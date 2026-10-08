"""
Check every authority and quotation in a draft against Indian Kanoon.

The rule throughout: say only what the source supports. If Indian Kanoon has
the case but doesn't list the reporter the draft cites, the result is "case
found, citation not confirmed", never "wrong citation".
"""

import time
from dataclasses import dataclass, field
from datetime import datetime

from .citations import Authority, Citation, case_name_before, find_authorities, find_citations
from .kanoon import BudgetExceeded, Doc, Hit, KanoonError
from .names import MATCH_THRESHOLD, name_query, name_score, short_title
from .quotes import Judgment, Quote, find_quotes

# status code -> (label shown to the user, severity)
STATUSES = {
    "VERIFIED": ("Verified", "ok"),
    "IDENTIFIED": ("Citation identified, case not named", "check"),
    "CASE_FOUND": ("Case found, citation not confirmed", "check"),
    "NEEDS_REVIEW": ("Needs a manual check", "check"),
    "WRONG_CITATION": ("Wrong citation", "problem"),
    "NAME_MISMATCH": ("Citation belongs to another case", "problem"),
    "NOT_FOUND": ("Not found", "problem"),
    "SKIPPED": ("Not checked", "check"),
    "QUOTE_VERIFIED": ("Quote matches", "ok"),
    "QUOTE_ALTERED": ("Quote wording differs", "problem"),
    "QUOTE_MISATTRIBUTED": ("Quote is from a different case", "problem"),
    "QUOTE_NOT_FOUND": ("Quote not in the judgment", "problem"),
    "QUOTE_UNCHECKED": ("Quote not checked", "check"),
}


def label(status: str) -> str:
    return STATUSES[status][0]


def severity(status: str) -> str:
    return STATUSES[status][1]


@dataclass
class CitationCheck:
    citation: Citation
    status: str  # confirmed | mismatch | unconfirmed
    note: str


@dataclass
class AuthorityResult:
    authority: Authority
    status: str
    headline: str
    match: Hit | None = None
    name_score: int | None = None
    citation_checks: list[CitationCheck] = field(default_factory=list)
    suggestion: str | None = None  # the correct citation, when Indian Kanoon lists one

    @property
    def severity(self):
        return severity(self.status)


@dataclass
class QuoteResult:
    quote: Quote
    status: str
    headline: str
    authority_label: str | None = None
    url: str | None = None
    changes: list[tuple[str, str]] = field(default_factory=list)

    @property
    def severity(self):
        return severity(self.status)


@dataclass
class Report:
    filename: str
    backend: str
    authorities: list[AuthorityResult]
    quotes: list[QuoteResult]
    seconds: float
    calls: dict
    cost_inr: float
    errors: list[str] = field(default_factory=list)

    def count(self, sev: str) -> int:
        return sum(r.severity == sev for r in self.authorities + self.quotes)


def _phrase_query(c: Citation) -> str:
    return " ORR ".join(f'"{p}"' for p in c.search_phrases())


def _date(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return iso or "date unknown"


def _join(items) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _cited_as(hits: list[Hit], keys: set[str]) -> str | None:
    """How other judgments name the case at this citation, read from their search snippets.
    Two snippets must agree before the name is trusted."""
    names = []
    for h in hits:
        for c in find_citations(h.headline):
            if c.key in keys:
                n = case_name_before(h.headline, c.start)
                if n:
                    names.append(n)
                break
    groups: list[list[str]] = []
    for n in names:
        for g in groups:
            if name_score(n, g[0]) >= MATCH_THRESHOLD:
                g.append(n)
                break
        else:
            groups.append([n])
    best = max(groups, key=len, default=[])
    return best[0] if len(best) >= 2 else None


class Checker:
    def __init__(self, backend):
        self.backend = backend
        self._docs: dict[int, Doc] = {}
        self._judgments: dict[int, Judgment] = {}

    def doc(self, tid: int) -> Doc:
        if tid not in self._docs:
            self._docs[tid] = self.backend.doc(tid)
        return self._docs[tid]

    def judgment(self, tid: int) -> Judgment:
        if tid not in self._judgments:
            self._judgments[tid] = Judgment(self.doc(tid))
        return self._judgments[tid]

    def listed_citations(self, tid: int) -> list[Citation]:
        return find_citations(self.doc(tid).equivalent_citations())

    # ------------------------------------------------------------------
    def authority(self, a: Authority) -> AuthorityResult:
        hits_by_cite = {c.key: self.backend.search(_phrase_query(c)) for c in a.citations}
        candidates = self._candidates(a.case_name, hits_by_cite) if a.case_name else []
        if candidates:
            return self._found_case(a, candidates, hits_by_cite)
        return self._case_not_found(a, hits_by_cite)

    def _candidates(self, name: str, hits_by_cite) -> list[tuple[Hit, int]]:
        """Indian Kanoon documents whose title names the same case, best first (at most three)."""
        scored: dict[int, tuple[Hit, int]] = {}

        def consider(hits):
            for h in hits:
                s = name_score(name, h.title)
                if s >= MATCH_THRESHOLD and (h.tid not in scored or s > scored[h.tid][1]):
                    scored[h.tid] = (h, s)

        for hits in hits_by_cite.values():
            consider(hits)
        if not scored:
            consider(self.backend.search(name_query(name)))
        return sorted(scored.values(), key=lambda x: -x[1])[:3]

    def _found_case(self, a, candidates, hits_by_cite) -> AuthorityResult:
        cited = {c.key for c in a.citations}

        def found_by_citation(tid):
            return any(h.tid == tid for c in a.citations for h in hits_by_cite[c.key])

        # Which candidate is the case the draft means? Prefer one Indian Kanoon ties to the citation.
        chosen = next((cand for cand in candidates if found_by_citation(cand[0].tid)), None)
        if chosen is None:
            chosen = next((cand for cand in candidates
                           if cited & {x.key for x in self.listed_citations(cand[0].tid)}), None)
        ambiguous = chosen is None and len(candidates) > 1
        hit, score = chosen or candidates[0]

        checks, suggestion, listed = [], None, None
        for c in a.citations:
            if any(h.tid == hit.tid for h in hits_by_cite[c.key]):
                checks.append(CitationCheck(c, "confirmed", "Indian Kanoon lists this citation for the case."))
                continue
            if listed is None:
                listed = self.listed_citations(hit.tid)
            if c.key in {x.key for x in listed}:
                checks.append(CitationCheck(c, "confirmed", "Indian Kanoon lists this citation for the case."))
                continue
            same = [x for x in listed if x.reporter == c.reporter]
            if same:
                suggestion = suggestion or same[0].conventional()
                checks.append(CitationCheck(c, "mismatch",
                                            f"Indian Kanoon lists this case at {same[0].conventional()}."))
            else:
                checks.append(CitationCheck(
                    c, "unconfirmed",
                    f"Indian Kanoon doesn't list a {c.reporter} citation for this case, "
                    "so the volume and page couldn't be checked."))

        title, when = short_title(hit.title), _date(hit.publishdate)
        confirmed = [x.citation.raw for x in checks if x.status == "confirmed"]
        unconfirmed = [x for x in checks if x.status == "unconfirmed"]
        mismatch = [x for x in checks if x.status == "mismatch"]
        if ambiguous:
            status = "NEEDS_REVIEW"
            headline = (f"Indian Kanoon has {len(candidates)} cases with this name, and none is listed at "
                        f"{_join(c.raw for c in a.citations)}. The closest is {title} ({when})"
                        + (f", listed at {suggestion}." if suggestion else ".")
                        + " Check which one you mean.")
        elif mismatch:
            status = "WRONG_CITATION"
            headline = (f"{title} ({when}) exists, but not at {mismatch[0].citation.raw}. "
                        f"Indian Kanoon lists it at {suggestion}.")
        elif not unconfirmed:
            status = "VERIFIED"
            headline = f"Matches {title} ({hit.docsource}, {when})."
        else:
            status = "CASE_FOUND"
            reporters = _join(sorted({x.citation.reporter for x in unconfirmed}))
            if confirmed:
                headline = (f"Matches {title} at {_join(confirmed)}. Indian Kanoon doesn't list its {reporters} "
                            f"citation, so {_join(x.citation.raw for x in unconfirmed)} couldn't be checked.")
            else:
                headline = (f"{title} ({when}) exists, but Indian Kanoon doesn't list its {reporters} citation, "
                            f"so {_join(x.citation.raw for x in unconfirmed)} couldn't be checked. "
                            "Check the volume and page against the reporter.")
        return AuthorityResult(a, status, headline, hit, score, checks, suggestion)

    def _case_not_found(self, a, hits_by_cite) -> AuthorityResult:
        seen, hits = set(), []
        for hs in hits_by_cite.values():
            for h in hs:
                if h.tid not in seen:
                    seen.add(h.tid)
                    hits.append(h)
        keys = {c.key for c in a.citations}
        for h in hits[:3]:  # does one of the results list this citation as its own?
            if keys & {x.key for x in self.listed_citations(h.tid)}:
                title = short_title(h.title)
                if a.case_name:
                    return AuthorityResult(a, "NAME_MISMATCH",
                                           f"This citation belongs to {title} ({_date(h.publishdate)}), "
                                           f"not {a.case_name}.", h)
                return AuthorityResult(a, "IDENTIFIED",
                                       f"The draft doesn't name the case. This citation is {title} "
                                       f"({_date(h.publishdate)}).", h)
        cited_as = _cited_as(hits, keys)
        if cited_as:
            others = f"Judgments on Indian Kanoon that cite {a.citations[0].raw} call it {cited_as}"
            if a.case_name and name_score(a.case_name, cited_as) < MATCH_THRESHOLD:
                return AuthorityResult(a, "NAME_MISMATCH", f"{others}, not {a.case_name}.")
            if not a.case_name:
                return AuthorityResult(a, "IDENTIFIED", f"The draft doesn't name the case. {others}.")
            return AuthorityResult(a, "NEEDS_REVIEW",
                                   f"{others}, which matches the draft, but the judgment itself couldn't be "
                                   "found on Indian Kanoon. Check it in the reporter.")
        if hits:
            who = f" under the name {a.case_name}" if a.case_name else ""
            return AuthorityResult(a, "NEEDS_REVIEW",
                                   "Other judgments on Indian Kanoon mention this citation, but the case itself "
                                   f"couldn't be found{who}. Check it by hand.")
        what = "Neither the citation nor the case name" if a.case_name else "The citation"
        return AuthorityResult(
            a, "NOT_FOUND",
            f"{what} could be found on Indian Kanoon. Confirm it exists in the reporter before filing: "
            "this is what an invented citation looks like.")

    # ------------------------------------------------------------------
    def quote(self, q: Quote, results: dict[int, AuthorityResult]) -> QuoteResult:
        # a NAME_MISMATCH match is some other case, so it can't stand in for the one the draft names
        resolved = {aid: r for aid, r in results.items() if r.match is not None and r.status != "NAME_MISMATCH"}
        target = results.get(q.authority_id)
        if target is None:
            return self._quote_anywhere(q, resolved, "The draft doesn't make clear which authority this quote is from.")
        if q.authority_id not in resolved:
            return QuoteResult(q, "QUOTE_UNCHECKED",
                               "Not checked: the authority it is attributed to couldn't be found.",
                               target.authority.label)
        name = short_title(target.match.title)
        j = self.judgment(target.match.tid)
        loc = j.locate(q.text)
        url = f"{target.match.url}#{loc.anchor}" if loc and loc.anchor else target.match.url
        if loc and loc.exact:
            return QuoteResult(q, "QUOTE_VERIFIED", f"Found word for word in {name}.", name, url)
        if loc and loc.score >= 75:
            return QuoteResult(q, "QUOTE_ALTERED",
                               f"A close passage is in {name}, but the wording differs.", name, url, loc.changes)
        for aid, other in resolved.items():
            if aid == q.authority_id:
                continue
            oloc = self.judgment(other.match.tid).locate(q.text)
            if oloc and (oloc.exact or oloc.score >= 90):
                oname = short_title(other.match.title)
                return QuoteResult(q, "QUOTE_MISATTRIBUTED",
                                   f"Not in {name}. This passage is from {oname}.", name,
                                   f"{other.match.url}#{oloc.anchor}", oloc.changes)
        return QuoteResult(q, "QUOTE_NOT_FOUND", f"No such passage in {name}.", name, target.match.url)

    def _quote_anywhere(self, q, resolved, why) -> QuoteResult:
        for r in resolved.values():
            loc = self.judgment(r.match.tid).locate(q.text)
            if loc and loc.exact:
                name = short_title(r.match.title)
                return QuoteResult(q, "QUOTE_VERIFIED", f"Found word for word in {name}.", name,
                                   f"{r.match.url}#{loc.anchor}")
        return QuoteResult(q, "QUOTE_UNCHECKED", why)


def check_text(text: str, backend, filename: str = "") -> Report:
    started = time.time()
    checker = Checker(backend)
    authorities = find_authorities(text)
    results: dict[int, AuthorityResult] = {}
    errors: list[str] = []
    for a in authorities:
        try:
            results[a.id] = checker.authority(a)
        except (BudgetExceeded, KanoonError) as exc:
            if str(exc) not in errors:
                errors.append(str(exc))
            results[a.id] = AuthorityResult(a, "SKIPPED", f"Not checked: {exc}")
    quote_results = []
    for q in find_quotes(text, authorities):
        try:
            quote_results.append(checker.quote(q, results))
        except (BudgetExceeded, KanoonError) as exc:
            if str(exc) not in errors:
                errors.append(str(exc))
            quote_results.append(QuoteResult(q, "QUOTE_UNCHECKED", f"Not checked: {exc}"))
    return Report(filename, backend.name, [results[a.id] for a in authorities], quote_results,
                  round(time.time() - started, 2), dict(backend.calls), backend.cost_inr, errors)
