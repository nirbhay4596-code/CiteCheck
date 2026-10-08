import pytest

from citecheck.kanoon import DemoKanoon
from citecheck.names import MATCH_THRESHOLD, name_score
from citecheck.quotes import Judgment


@pytest.mark.parametrize("draft, title", [
    ("Shreya Singhal v. Union of India", "Shreya Singhal vs U.O.I on 24 March, 2015"),
    ("Lalita Kumari v. Government of Uttar Pradesh & Ors.", "Lalita Kumari vs Govt.Of U.P.& Ors on 12 November, 2013"),
    ("D.K. Basu v. State of W.B.", "Shri D.K. Basu,Ashok K. Johri vs State Of West Bengal,State Of U.P on 18 December, 1996"),
    ("Vishaka v. State of Rajasthan", "Vishaka & Ors vs State Of Rajasthan & Ors on 13 August, 1997"),
    ("Vishakha v. State of Rajasthan", "Vishaka & Ors vs State Of Rajasthan & Ors on 13 August, 1997"),
    ("K.S. Puttaswamy (Retd.) v. Union of India", "Justice K.S.Puttaswamy(Retd) vs Union Of India on 26 September, 2018"),
])
def test_same_case_spelled_differently(draft, title):
    assert name_score(draft, title) >= MATCH_THRESHOLD


@pytest.mark.parametrize("draft, title", [
    ("Kavita Arora v. Union of India", "Shreya Singhal vs U.O.I on 24 March, 2015"),
    ("Ramesh Sharma v. State of U.P.", "Rajesh Sharma vs State Of U.P. on 27 July, 2017"),
    ("Arnesh Kumar v. State of Bihar", "Arnesh Kumar vs Union Of India on 1 January, 2019"),
    ("Rakesh Malhotra v. State of Haryana", "Arnesh Kumar vs State Of Bihar & Anr on 2 July, 2014"),
])
def test_different_cases_do_not_match(draft, title):
    assert name_score(draft, title) < MATCH_THRESHOLD


@pytest.fixture(scope="module")
def arnesh():
    return Judgment(DemoKanoon().docs[2982624])


def test_exact_quote(arnesh):
    loc = arnesh.locate("Our endeavour in this judgment is to ensure that police officers do not arrest "
                        "accused unnecessarily and Magistrate do not authorise detention casually and mechanically.")
    assert loc.exact and loc.anchor == "p_12"


def test_one_word_changed_is_caught(arnesh):
    loc = arnesh.locate("We believe that no arrest should be made merely because the offence is non-bailable "
                        "and cognizable")
    assert not loc.exact
    assert loc.changes == [("merely", "only")]


def test_ellipsis_and_brackets_are_allowed(arnesh):
    loc = arnesh.locate("We believe that no arrest should be made ... because the offence is non-bailable "
                        "and cognizable and therefore, lawful for [the police] to do so.")
    assert loc.exact


def test_invented_quote_is_not_found(arnesh):
    loc = arnesh.locate("The power of arrest must be exercised sparingly and only after reasons are recorded "
                        "in writing that custodial interrogation is indispensable.")
    assert loc is None or loc.score < 75
