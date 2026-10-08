"""
Indian Kanoon access.

Two backends with the same interface:

* LiveKanoon  -- the paid Indian Kanoon API (https://api.indiankanoon.org).
                 Every response is cached on disk, so re-checking a draft costs
                 nothing, and a daily call limit protects your credit.
* DemoKanoon  -- an offline corpus of saved judgments. Free, needs no token;
                 used for the sample drafts and the test suite.
"""

import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

API_BASE = "https://api.indiankanoon.org"
COST_INR = {"search": 0.50, "doc": 0.20}  # published per-request prices
DEMO_CORPUS = Path(__file__).parent / "data" / "demo_corpus"


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def flatten_spaces(s: str) -> str:
    for bad, good in ((" ", " "), (" ", " "), ("​", ""), ("­", "")):
        s = s.replace(bad, good)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Hit:
    tid: int
    title: str
    docsource: str = ""
    publishdate: str = ""
    headline: str = ""  # text around the match, as Indian Kanoon's search results show it

    @property
    def url(self) -> str:
        return f"https://indiankanoon.org/doc/{self.tid}/"


@dataclass
class Doc:
    tid: int
    title: str
    docsource: str
    publishdate: str
    html: str

    @property
    def url(self) -> str:
        return f"https://indiankanoon.org/doc/{self.tid}/"

    def equivalent_citations(self) -> str:
        m = re.search(r'(?is)<h3 class="doc_citations">(.*?)</h3>', self.html)
        if m:
            return strip_tags(m.group(1)).replace("Equivalent citations:", "").strip()
        m = re.search(r"Equivalent citations:([^\n<]*)", strip_tags(self.html))
        return m.group(1).strip() if m else ""

    def paragraphs(self) -> list[tuple[str, str]]:
        """(anchor, text) for every paragraph, block quote and preformatted block, in order."""
        out = []
        rx = r'(?is)<(p|blockquote|pre)\b[^>]*\bid="((?:p|blockquote|pre)_\d+)"[^>]*>(.*?)</\1>'
        for m in re.finditer(rx, self.html):
            text = flatten_spaces(strip_tags(m.group(3)))
            if text:
                out.append((m.group(2), text))
        if not out:  # no anchors: fall back to the whole text as one block
            out.append(("", flatten_spaces(strip_tags(self.html))))
        return out


class BudgetExceeded(RuntimeError):
    pass


class KanoonError(RuntimeError):
    pass


class LiveKanoon:
    name = "Indian Kanoon (live)"

    def __init__(self, token: str, cache_dir: str | os.PathLike = ".cache/kanoon",
                 daily_call_limit: int = 100, timeout: int = 45):
        import requests  # imported here so the demo mode needs no network library

        self._requests = requests
        self.token = token
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.daily_call_limit = daily_call_limit
        self.timeout = timeout
        self.calls = {"search": 0, "doc": 0, "cached": 0}

    # -- spend tracking ----------------------------------------------------
    def _usage_path(self) -> Path:
        return self.cache / f"usage-{date.today().isoformat()}.json"

    def calls_today(self) -> int:
        try:
            return json.loads(self._usage_path().read_text())["calls"]
        except (OSError, ValueError, KeyError):
            return 0

    def _count_call(self):
        n = self.calls_today() + 1
        self._usage_path().write_text(json.dumps({"calls": n}))

    @property
    def cost_inr(self) -> float:
        return sum(COST_INR[k] * self.calls[k] for k in COST_INR)

    # -- transport ---------------------------------------------------------
    def _post(self, path: str, params: dict, kind: str) -> dict:
        key = hashlib.sha1(json.dumps([path, params], sort_keys=True).encode()).hexdigest()
        cached = self.cache / f"{key}.json"
        if cached.exists():
            self.calls["cached"] += 1
            return json.loads(cached.read_text(encoding="utf-8"))
        if self.calls_today() >= self.daily_call_limit:
            raise BudgetExceeded(f"Daily limit of {self.daily_call_limit} Indian Kanoon calls reached.")
        try:
            resp = self._requests.post(
                API_BASE + path, params=params, timeout=self.timeout,
                headers={"Authorization": "Token " + self.token, "Accept": "application/json"},
            )
        except self._requests.RequestException as exc:
            raise KanoonError(f"Network error calling Indian Kanoon: {exc}") from exc
        self._count_call()
        if resp.status_code != 200:
            hint = {401: "token rejected", 403: "out of credit or token not activated",
                    429: "rate limited"}.get(resp.status_code, "")
            raise KanoonError(f"Indian Kanoon returned HTTP {resp.status_code} {hint}".strip())
        self.calls[kind] += 1
        data = resp.json()
        cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def search(self, query: str) -> list[Hit]:
        data = self._post("/search/", {"formInput": query, "pagenum": 0}, "search")
        return [Hit(int(d["tid"]), strip_tags(d.get("title", "")), strip_tags(d.get("docsource", "")),
                    d.get("publishdate") or "", flatten_spaces(strip_tags(d.get("headline", ""))))
                for d in data.get("docs") or []]

    def doc(self, tid: int) -> Doc:
        data = self._post(f"/doc/{tid}/", {"maxcites": 0, "maxcitedby": 0}, "doc")
        return Doc(int(tid), strip_tags(data.get("title", "")), strip_tags(data.get("docsource", "")),
                   data.get("publishdate") or "", data.get("doc") or "")


def _tokens(s: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", s.lower())) + " "


class DemoKanoon:
    """Offline stand-in for the API, searching a small corpus of saved judgments."""

    name = "Demo library (offline)"
    daily_call_limit = None

    def __init__(self, corpus_dir: str | os.PathLike = DEMO_CORPUS):
        self.docs: dict[int, Doc] = {}
        self._title_tokens: dict[int, str] = {}
        self._all_tokens: dict[int, str] = {}
        self._text: dict[int, str] = {}
        for f in sorted(Path(corpus_dir).glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            doc = Doc(int(d["tid"]), d["title"], d["docsource"], d["publishdate"], d["doc"])
            self.docs[doc.tid] = doc
            self._text[doc.tid] = flatten_spaces(strip_tags(doc.html))
            self._title_tokens[doc.tid] = _tokens(doc.title)
            self._all_tokens[doc.tid] = _tokens(self._text[doc.tid])
        self.calls = {"search": 0, "doc": 0, "cached": 0}
        self.cost_inr = 0.0

    def calls_today(self) -> int:
        return 0

    def search(self, query: str) -> list[Hit]:
        """Mimics Indian Kanoon's syntax closely enough for the verifier:
        "quoted phrases", ORR between alternatives, doctypes: filters ignored."""
        self.calls["search"] += 1
        query = re.sub(r"\bdoctypes:\s*\S+", "", query)
        alternatives = [a.strip() for a in re.split(r"\s+ORR\s+", query) if a.strip()]
        scored = []
        for tid in self.docs:
            matched_words = None
            for alt in alternatives:
                phrase = re.fullmatch(r'"(.*)"', alt)
                words = _tokens(phrase.group(1) if phrase else alt).split()
                if phrase and f" {' '.join(words)} " in self._all_tokens[tid]:
                    matched_words = words
                elif not phrase and words and all(f" {w} " in self._all_tokens[tid] for w in words):
                    matched_words = words[:1]
                if matched_words:
                    break
            if matched_words:
                words = _tokens(" ".join(alternatives)).split()
                overlap = sum(f" {w} " in self._title_tokens[tid] for w in words)
                scored.append((-overlap, tid, matched_words))
        return [self._hit(tid, words) for _, tid, words in sorted(scored)[:10]]

    def _hit(self, tid: int, words: list[str]) -> Hit:
        d = self.docs[tid]
        # headline: the text around the first match, like Indian Kanoon's search snippets
        rx = r"\W+".join(re.escape(w) for w in words)
        m = re.search(rf"(?i)(?<![a-z0-9]){rx}(?![a-z0-9])", self._text[tid])
        headline = self._text[tid][max(0, m.start() - 200):m.end() + 100] if m else ""
        return Hit(d.tid, d.title, d.docsource, d.publishdate, headline)

    def doc(self, tid: int) -> Doc:
        self.calls["doc"] += 1
        return self.docs[int(tid)]
