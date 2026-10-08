"""
Find case citations in a draft, without any AI.

Indian law reports follow a small number of fixed formats, so pattern matching
is enough to find them, and it is deterministic: the same draft always gives the
same result, and nothing can be invented along the way.

Every citation is reduced to a canonical key (reporter|year|volume|page), so
"(2014) 8 SCC 273" in a draft and "2014 (8) SCC 273" on Indian Kanoon compare
as equal.
"""

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Reporter patterns. Each yields named groups: year, vol (optional),
# court (optional), page, series (optional), supp (optional).
# --------------------------------------------------------------------------

_SCC = r"S\.?\s?C\.?\s?C\.?"
_SCR = r"S\.?\s?C\.?\s?R\.?"
_SERIES = r"(?P<series>\s*\((?:Cri|Crl|L\s?&\s?S|Civ|Tax)\.?\))?"
_SUPP = r"(?P<supp>Supp\.?\s*)"

PATTERNS = [
    # 2023 SCC OnLine SC 1234 / 2019 SCC OnLine Del 4567
    ("SCC OnLine", r"(?P<year>(?:19|20)\d{2})\s+SCC\s*On\s?Line\s+(?P<court>[A-Z][A-Za-z&.]*(?:\s[A-Z][A-Za-z&.]*)?)\s+(?P<page>\d+)"),
    # 1992 Supp (3) SCC 217 / (1992) Supp 3 SCC 217
    ("SCC", r"(?P<year>(?:18|19|20)\d{2})\s+" + _SUPP + r"\(?(?P<vol>\d{1,2})?\)?\s*" + _SCC + _SERIES + r"\s+(?P<page>\d+)"),
    ("SCC", r"\((?P<year>(?:18|19|20)\d{2})\)\s*" + _SUPP + r"(?P<vol>\d{1,2})?\s*" + _SCC + _SERIES + r"\s+(?P<page>\d+)"),
    # (2014) 8 SCC 273 / (2014) 3 SCC (Cri) 449
    ("SCC", r"[\(\[](?P<year>(?:18|19|20)\d{2})[\)\]]\s*(?P<vol>\d{1,2})\s*" + _SCC + _SERIES + r"\s+(?P<page>\d+)"),
    # 2014 (8) SCC 273 -- the format Indian Kanoon uses
    ("SCC", r"(?P<year>(?:18|19|20)\d{2})\s*\((?P<vol>\d{1,2})\)\s*" + _SCC + _SERIES + r"\s+(?P<page>\d+)"),
    # AIR 2014 SC 2756 / AIR 2014 SUPREME COURT 2756 / AIR 2010 Del 45
    ("AIR", r"A\.?\s?I\.?\s?R\.?\s+(?P<year>(?:19|20)\d{2})\s+(?P<court>SUPREME\s+COURT|S\.\s?C\.|SC|[A-Z][A-Za-z&]+\.?)(?P<series>\s*\((?:CRIMINAL|CRI|Cri|SUPP|Supp)\.?\))?\s+(?P<page>\d+)"),
    # 2014 AIR SCW 3930
    ("AIR SCW", r"(?P<year>(?:19|20)\d{2})\s+AIR\s+SCW\s+(?P<page>\d+)"),
    # 1978 AIR 597 -- older Indian Kanoon style, court implied (Supreme Court)
    ("AIR", r"(?P<year>(?:19|20)\d{2})\s+AIR\s+(?P<page>\d+)"),
    # (1978) 2 SCR 621 / [1978] 2 SCR 621 / [1973] Supp SCR 1
    ("SCR", r"[\(\[](?P<year>(?:18|19|20)\d{2})[\)\]]\s*" + _SUPP + r"?(?P<vol>\d{1,2})?\s*" + _SCR + r"\s+(?P<page>\d+)"),
    # 1978 SCR (2) 621 -- Indian Kanoon style
    ("SCR", r"(?P<year>(?:18|19|20)\d{2})\s+" + _SCR + r"\s*\((?P<vol>\d{1,2})\)\s*(?P<page>\d+)"),
    # 2024 INSC 123 -- Supreme Court neutral citation
    ("INSC", r"(?P<year>20\d{2})\s+INSC\s+(?P<page>\d+)"),
    # (2014) 8 SCALE 250 / 2014 (8) SCALE 250
    ("SCALE", r"\((?P<year>(?:19|20)\d{2})\)\s*(?P<vol>\d{1,2})\s*SCALE\s+(?P<page>\d+)"),
    ("SCALE", r"(?P<year>(?:19|20)\d{2})\s*\((?P<vol>\d{1,2})\)\s*SCALE\s+(?P<page>\d+)"),
    # JT 1997 (7) SC 384 / (1997) 7 JT 384
    ("JT", r"J\.?T\.?\s+(?P<year>(?:19|20)\d{2})\s*\((?P<vol>\d{1,2})\)\s*S\.?C\.?\s+(?P<page>\d+)"),
    ("JT", r"\((?P<year>(?:19|20)\d{2})\)\s*(?P<vol>\d{1,2})\s*J\.?T\.?\s+(?P<page>\d+)"),
    # MANU/SC/0133/1978
    ("MANU", r"MANU/(?P<court>[A-Z]{2,5})/(?P<page>\d{3,5})/(?P<year>(?:19|20)\d{2})"),
    # 2004 Cri LJ 1234
    ("Cri LJ", r"(?P<year>(?:19|20)\d{2})\s+CRI\.?\s?L\.?\s?J\.?\s+(?P<page>\d+)"),
    # (2014) 210 DLT 599
    ("DLT", r"\((?P<year>(?:19|20)\d{2})\)\s*(?P<vol>\d{1,3})\s*DLT\s+(?P<page>\d+)"),
]

_COMPILED = [(rep, re.compile(r"(?<![\w/])" + pat + r"(?!\d)", re.IGNORECASE)) for rep, pat in PATTERNS]

_COURT_ALIASES = {"SUPREMECOURT": "SC", "SC": "SC"}


def _court(raw):
    if not raw:
        return None
    c = re.sub(r"[\s.]", "", raw).upper()
    return _COURT_ALIASES.get(c, c)


def _series(raw):
    if not raw:
        return ""
    s = re.sub(r"[\s.()]", "", raw).upper()
    return {"CRL": "CRI", "CRIMINAL": "CRI"}.get(s, s)


@dataclass
class Citation:
    raw: str
    reporter: str           # e.g. "SCC", "SCC (CRI)", "AIR", "SCR"
    year: int
    volume: str | None
    court: str | None
    page: str
    supp: bool
    start: int
    end: int

    @property
    def key(self) -> str:
        vol = ("SUPP" if self.supp else "") + (self.volume or "")
        court = self.court or ""
        if self.reporter == "AIR" and court in ("", "SC"):
            court = "SC"  # "1978 AIR 597" means the Supreme Court
        return "|".join([self.reporter, str(self.year), vol, court, self.page])

    def search_phrases(self) -> list[str]:
        """Token sequences a search engine that ignores punctuation would match."""
        y, v, p = self.year, self.volume or "", self.page
        supp = "Supp " if self.supp else ""
        if self.reporter.startswith("SCC (") or self.reporter == "SCC":
            series = self.reporter[4:].strip("() ") if self.reporter != "SCC" else ""
            return [f"{y} {supp}{v} SCC {series} {p}".replace("  ", " ")]
        if self.reporter == "SCC OnLine":
            return [f"{y} SCC OnLine {self.court} {p}"]
        if self.reporter == "AIR":
            if self.court in (None, "SC"):
                return [f"AIR {y} SC {p}", f"AIR {y} SUPREME COURT {p}", f"{y} AIR {p}"]
            return [f"AIR {y} {self.court} {p}"]
        if self.reporter == "SCR":
            return [f"{y} {supp}{v} SCR {p}", f"{y} SCR {v} {p}"]
        if self.reporter in ("SCALE", "DLT"):
            return [f"{y} {v} {self.reporter} {p}"]
        if self.reporter == "JT":
            return [f"JT {y} {v} SC {p}", f"{y} {v} JT {p}"]
        if self.reporter == "MANU":
            return [f"MANU {self.court} {p} {y}"]
        return [f"{y} {self.reporter} {p}"]

    def conventional(self) -> str:
        """The form a lawyer would write, e.g. '(2014) 2 SCC 1' rather than Indian Kanoon's '2014 (2) SCC 1'."""
        y, v, p = self.year, self.volume or "", self.page
        supp = "Supp " if self.supp else ""
        if self.reporter.startswith("SCC"):
            series = f" ({self.reporter[5:-1].title()})" if self.reporter != "SCC" else ""
            if self.supp:
                return f"{y} Supp ({v}) SCC{series} {p}"
            return f"({y}) {v} SCC{series} {p}"
        if self.reporter == "AIR":
            return f"AIR {y} {self.court or 'SC'} {p}"
        if self.reporter == "SCR":
            return f"({y}) {supp}{v} SCR {p}".replace("  ", " ")
        if self.reporter in ("SCALE", "DLT"):
            return f"({y}) {v} {self.reporter} {p}"
        return self.raw


def find_citations(text: str) -> list[Citation]:
    found = []
    for reporter, rx in _COMPILED:
        for m in rx.finditer(text):
            g = m.groupdict()
            series = _series(g.get("series"))
            rep = reporter
            if reporter == "SCC" and series:
                rep = f"SCC ({series})"
            elif reporter == "AIR" and series:
                rep = f"AIR ({series})"
            found.append(Citation(
                raw=re.sub(r"\s+", " ", m.group(0)).strip(),
                reporter=rep,
                year=int(g["year"]),
                volume=g.get("vol"),
                court=_court(g.get("court")),
                page=g["page"].lstrip("0") or "0",
                supp=bool(g.get("supp")),
                start=m.start(),
                end=m.end(),
            ))
    # keep the longest match where patterns overlap
    found.sort(key=lambda c: (c.start, -(c.end - c.start)))
    kept: list[Citation] = []
    for c in found:
        if kept and c.start < kept[-1].end:
            continue
        kept.append(c)
    return kept


def parse_citation_list(text: str) -> set[str]:
    """Canonical keys for a list such as Indian Kanoon's 'Equivalent citations' line."""
    return {c.key for c in find_citations(text)}


# --------------------------------------------------------------------------
# Case names
# --------------------------------------------------------------------------

_V = re.compile(r"\s(?:v\.?|vs\.?|v/s\.?|versus)\s", re.IGNORECASE)
_TRAIL = re.compile(r"(?:[\s,:;(\[*_\"'“”‘’]|reported\s+(?:in|as|at)|cited\s+as|\bat\b)*$", re.IGNORECASE)
_CONNECTORS = {"of", "and", "&", "the", "for", "through", "thr.", "by", "de", "ors.", "ors", "anr.", "anr",
               "others", "another", "etc.", "lrs.", "lrs", "(dead)", "(retd.)", "(retd)", "rep.", "m/s.", "m/s"}
_STOP = {"in", "see", "also", "cf.", "cf", "court", "hon'ble", "apex", "judgment", "decision", "case",
         "held", "that", "this", "these", "where", "relied", "upon", "per", "e.g.", "i.e.", "vide", "where"}
_ABBREV = re.compile(r"^(?:[A-Z]\.){1,4}$|^(?:Ltd|Co|Pvt|Anr|Ors|Dr|Mr|Mrs|Smt|Shri|Sri|Govt|Corpn|Retd|Lrs|St|No|U\.P|M\.P)\.?,?$")


def _petitioner(before: str) -> str:
    tokens = before.split()
    taken: list[str] = []
    for tok in reversed(tokens[-14:]):
        bare = tok.strip(",;:*_\"'“”‘’")
        low = bare.lower()
        if not bare or tok.endswith((";", ":")):
            break  # a semicolon or colon closes the previous authority
        if low in _STOP:
            break
        is_name_word = bare[0].isupper() or bare[0].isdigit() or bare[0] in "(&"
        if not (is_name_word or low in _CONNECTORS):
            break
        # a sentence-ending word ("Act.") before an already-taken capital starts a new sentence
        if taken and bare.endswith(".") and not _ABBREV.match(bare):
            break
        taken.append(bare)
    while taken and taken[-1].lower() in _CONNECTORS:
        taken.pop()  # trim leading connectors ("by", "of")
    return " ".join(reversed(taken))


_RESPONDENT_LOWER = _CONNECTORS | {"its", "in", "at", "on", "to", "represented", "rep", "dead", "retd"}


def _plausible_respondent(respondent: str) -> bool:
    if not respondent or len(respondent) > 110:
        return False
    if re.search(r"\b(?:18|19|20)\d{2}\b", respondent):
        return False  # runs into an earlier citation
    for word in respondent.split():
        bare = word.strip(",;:.()*_\"'“”‘’")
        if bare and bare[0].islower() and bare.lower() not in _RESPONDENT_LOWER:
            return False  # ordinary prose, not a party name
    return True


def case_name_before(text: str, start: int, floor: int = 0) -> str | None:
    window = text[max(floor, start - 220):start]
    window = window.replace("\n", " ")
    window = _TRAIL.sub("", window)
    marks = list(_V.finditer(window))
    if not marks:
        return None
    m = marks[-1]
    respondent = window[m.end():].strip(" ,;:*_\"'“”‘’")
    if not _plausible_respondent(respondent):
        return None
    petitioner = _petitioner(window[:m.start()])
    if not petitioner:
        return None
    return f"{petitioner} v. {respondent}".strip()


# --------------------------------------------------------------------------
# Authorities: a case name plus its parallel citations
# --------------------------------------------------------------------------

_PARALLEL_GAP = re.compile(r"^[\s,:=&]*(?:and|also\s+reported\s+(?:in|as)|reported\s+in)?[\s,:=]*$", re.IGNORECASE)


@dataclass
class Authority:
    id: int
    case_name: str | None
    citations: list[Citation] = field(default_factory=list)

    @property
    def start(self):
        return self.citations[0].start

    @property
    def end(self):
        return self.citations[-1].end

    @property
    def label(self):
        cites = " : ".join(c.raw for c in self.citations)
        return f"{self.case_name}, {cites}" if self.case_name else cites


def find_authorities(text: str) -> list[Authority]:
    authorities: list[Authority] = []
    for c in find_citations(text):
        prev = authorities[-1] if authorities else None
        if (prev and (c.start - prev.end) < 40 and _PARALLEL_GAP.match(text[prev.end:c.start])
                and c.reporter not in {x.reporter for x in prev.citations}):
            prev.citations.append(c)  # parallel citation of the same case
            continue
        floor = prev.end if prev else 0
        authorities.append(Authority(id=len(authorities) + 1,
                                     case_name=case_name_before(text, c.start, floor), citations=[c]))
    return authorities


# "Arnesh Kumar (supra)" -- a back-reference used to attribute quotes
SUPRA = re.compile(r"([A-Z][\w.&'’-]*(?:\s+(?:[A-Z][\w.&'’-]*|of|and|v\.|vs\.?))*)\s*,?\s*\(?\s*supra\s*\)?", re.UNICODE)
