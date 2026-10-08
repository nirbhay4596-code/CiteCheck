"""
The live API behaves differently from the demo library: a citation search returns the
judgments that *cite* a case, often ranked above the case itself, and many cases share a
name. These tests replay that behaviour with a scripted backend.
"""

import json

import pytest

from citecheck.kanoon import BudgetExceeded, DemoKanoon, Doc, Hit, KanoonError, LiveKanoon
from citecheck.verify import check_text


class Scripted:
    name = "scripted"

    def __init__(self, searches: dict[str, list[Hit]], docs: dict[int, Doc]):
        self.searches, self.docs = searches, docs
        self.calls = {"search": 0, "doc": 0, "cached": 0}
        self.cost_inr = 0.0

    def search(self, query):
        self.calls["search"] += 1
        for needle, hits in self.searches.items():
            if needle in query:
                return hits
        return []

    def doc(self, tid):
        self.calls["doc"] += 1
        return self.docs[tid]


def doc(tid, title, citations):
    return Doc(tid, title, "Supreme Court of India", "2000-01-01",
               f'<h3 class="doc_citations">Equivalent citations: {citations}</h3><p id="p_1">Text.</p>')


DEMO = DemoKanoon()
ARNESH = DEMO.docs[2982624]


def test_case_found_by_name_when_citing_judgments_crowd_the_citation_search():
    citing = [Hit(1, "Rajesh vs State Of U.P. on 1 January, 2020"), Hit(2, "Mohan vs State on 2 June, 2021")]
    backend = Scripted(
        {'"2014 8 SCC 273"': citing,
         "arnesh kumar": [Hit(2982624, ARNESH.title)]},
        {1: doc(1, citing[0].title, "2020 (1) SCC 10"), 2: doc(2, citing[1].title, "2021 (4) SCC 20"),
         2982624: ARNESH})
    [r] = check_text("Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273", backend).authorities
    assert r.status == "VERIFIED"


def test_cases_sharing_a_name_need_review_not_a_wrong_citation_flag():
    a = doc(11, "State Of Punjab vs Gurnam Singh on 3 May, 1999", "1999 (6) SCC 172")
    b = doc(12, "State Of Punjab vs Gurnam Singh on 9 August, 2003", "2003 (2) SCC 100")
    backend = Scripted({"punjab gurnam singh": [Hit(11, a.title), Hit(12, b.title)]}, {11: a, 12: b})
    [r] = check_text("State of Punjab v. Gurnam Singh, (1999) 6 SCC 999", backend).authorities
    assert r.status == "NEEDS_REVIEW"


def test_single_case_with_a_different_page_is_a_wrong_citation():
    a = doc(11, "State Of Punjab vs Gurnam Singh on 3 May, 1999", "1999 (6) SCC 172")
    backend = Scripted({"punjab gurnam singh": [Hit(11, a.title)]}, {11: a})
    [r] = check_text("State of Punjab v. Gurnam Singh, (1999) 6 SCC 999", backend).authorities
    assert r.status == "WRONG_CITATION"
    assert r.suggestion == "(1999) 6 SCC 172"


def test_name_mismatch_inferred_from_how_other_judgments_cite_it():
    snippet = "as held in Shreya Singhal v. Union of India, (2015) 5 SCC 1, the provision"
    citing = [Hit(i, f"Citing judgment {i} vs State on 1 January, 2020", headline=snippet) for i in (21, 22, 23)]
    backend = Scripted({'"2015 5 SCC 1"': citing},
                       {h.tid: doc(h.tid, h.title, "2020 (1) SCC 1") for h in citing})
    [r] = check_text("Kavita Arora v. Union of India, (2015) 5 SCC 1", backend).authorities
    assert r.status == "NAME_MISMATCH"
    assert "Shreya Singhal" in r.headline


def test_invented_name_on_a_real_citation_is_a_mismatch_even_when_the_name_exists():
    """The live shape that the first real run exposed (draft B, Kavita Arora).

    A case really does carry the invented name, so it becomes a name candidate, but Indian
    Kanoon lists the cited citation as another judgment's own. That is a mismatch, not merely
    "citation not confirmed": the source states whose citation it is.
    """
    owner = doc(110813550, "Shreya Singhal vs U.O.I on 24 March, 2015", "(2015) 5 SCC 1")
    namesake = doc(45851935, "Dr Kavita Arora & Anr vs Union Of India & Anr on 8 October, 2020", "")
    backend = Scripted(
        {'"2015 5 SCC 1"': [Hit(owner.tid, owner.title)],
         "kavita arora": [Hit(namesake.tid, namesake.title)]},
        {owner.tid: owner, namesake.tid: namesake})
    [r] = check_text("Kavita Arora v. Union of India, (2015) 5 SCC 1", backend).authorities
    assert r.status == "NAME_MISMATCH"
    assert "Shreya Singhal" in r.headline
    assert "Kavita Arora" in r.headline  # the namesake is still reported, so the user isn't misled


def test_unlistable_citation_stays_case_found_when_it_belongs_to_nobody():
    """The mismatch check must not over-fire: if no judgment claims the citation, the honest
    answer is still "case found, citation not confirmed" (rule 2)."""
    namesake = doc(31, "Kavita Arora vs Union Of India on 8 October, 2020", "")
    other = doc(32, "Unrelated vs State on 1 January, 2020", "2020 (1) SCC 10")
    backend = Scripted(
        {'"2015 5 SCC 1"': [Hit(other.tid, other.title)],
         "kavita arora": [Hit(namesake.tid, namesake.title)]},
        {namesake.tid: namesake, other.tid: other})
    [r] = check_text("Kavita Arora v. Union of India, (2015) 5 SCC 1", backend).authorities
    assert r.status == "CASE_FOUND"


def test_nothing_anywhere_is_not_found():
    [r] = check_text("Rakesh Malhotra v. State of Haryana, (2016) 11 SCC 742", Scripted({}, {})).authorities
    assert r.status == "NOT_FOUND"


# -- LiveKanoon transport: caching, the daily limit, errors -----------------------------

class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


@pytest.fixture
def http(monkeypatch):
    calls = []

    def fake_post(url, params=None, headers=None, timeout=None):
        calls.append(url)
        if "/doc/" in url:
            return FakeResponse(200, {"tid": 5, "title": "A vs B", "doc": "<p id='p_1'>x</p>"})
        if params and params.get("formInput") == "broke":
            return FakeResponse(403, {})
        return FakeResponse(200, {"docs": [{"tid": 5, "title": "<b>A</b> vs B", "headline": "<b>x</b>"}]})

    monkeypatch.setattr("requests.post", fake_post)
    return calls


def test_responses_are_cached(http, tmp_path):
    k = LiveKanoon("token", tmp_path, daily_call_limit=10)
    assert k.search("A vs B")[0].title == "A vs B"
    k.search("A vs B")
    assert len(http) == 1 and k.calls["cached"] == 1
    assert k.cost_inr == pytest.approx(0.50)


def test_daily_limit_stops_spending(http, tmp_path):
    k = LiveKanoon("token", tmp_path, daily_call_limit=2)
    k.search("one")
    k.doc(5)
    with pytest.raises(BudgetExceeded):
        k.search("three")
    assert len(http) == 2


def test_http_errors_are_explained(http, tmp_path):
    with pytest.raises(KanoonError, match="out of credit"):
        LiveKanoon("token", tmp_path).search("broke")


def test_budget_errors_become_skipped_rows_not_crashes(http, tmp_path):
    k = LiveKanoon("token", tmp_path, daily_call_limit=0)
    report = check_text("Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273", k)
    assert report.authorities[0].status == "SKIPPED"
    assert report.errors and json.dumps(report.errors)
