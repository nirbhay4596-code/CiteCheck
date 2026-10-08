import pytest

from citecheck.citations import find_authorities, find_citations, parse_citation_list


@pytest.mark.parametrize("draft_form, ik_form", [
    ("(2014) 8 SCC 273", "2014 (8) SCC 273"),
    ("AIR 1978 SC 597", "1978 AIR 597"),
    ("AIR 2014 SC 2756", "AIR 2014 SUPREME COURT 2756"),
    ("(1978) 2 SCR 621", "1978 SCR (2) 621"),
    ("[1978] 2 SCR 621", "1978 SCR (2) 621"),
    ("(1997) 5 SCALE 453", "1997 (5) SCALE 453"),
    ("(2014) 3 SCC (Cri) 449", "2014 (3) SCC (CRI) 449"),
    ("1992 Supp (3) SCC 217", "1992 Supp (3) SCC 217"),
    ("[1997] 1 SCC 416", "1997 (1) SCC 416"),
])
def test_draft_and_indian_kanoon_forms_compare_equal(draft_form, ik_form):
    assert parse_citation_list(draft_form) == parse_citation_list(ik_form)
    assert len(parse_citation_list(draft_form)) == 1


def test_different_series_and_pages_stay_different():
    keys = parse_citation_list("(2014) 8 SCC 273, (2014) 8 SCC 2735, (2014) 3 SCC (Cri) 273")
    assert len(keys) == 3


@pytest.mark.parametrize("text, reporter", [
    ("2023 SCC OnLine SC 1234", "SCC OnLine"),
    ("2019 SCC OnLine Del 4567", "SCC OnLine"),
    ("2024 INSC 55", "INSC"),
    ("MANU/SC/0133/1978", "MANU"),
    ("JT 1997 (7) SC 384", "JT"),
    ("2004 Cri LJ 1234", "Cri LJ"),
    ("(2014) 210 DLT 599", "DLT"),
    ("2014 AIR SCW 3930", "AIR SCW"),
])
def test_other_reporters(text, reporter):
    [c] = find_citations(text)
    assert c.reporter == reporter


def test_conventional_form():
    [c] = find_citations("2014 (2) SCC 1")
    assert c.conventional() == "(2014) 2 SCC 1"


def test_case_names_and_parallel_citations():
    text = ("In Arnesh Kumar v. State of Bihar & Anr., (2014) 8 SCC 273 : AIR 2014 SC 2756, the Court held. "
            "See also Maneka Gandhi vs. Union of India, AIR 1978 SC 597 and D.K. Basu v. State of W.B., "
            "[1997] 1 SCC 416. In Lalita Kumari v. Govt. of U.P. (2014) 2 SCC 1 the Court held. "
            "The judgment reported as (2015) 5 SCC 1 is clear.")
    got = [(a.case_name, [c.raw for c in a.citations]) for a in find_authorities(text)]
    assert got == [
        ("Arnesh Kumar v. State of Bihar & Anr.", ["(2014) 8 SCC 273", "AIR 2014 SC 2756"]),
        ("Maneka Gandhi v. Union of India", ["AIR 1978 SC 597"]),
        ("D.K. Basu v. State of W.B.", ["[1997] 1 SCC 416"]),
        ("Lalita Kumari v. Govt. of U.P.", ["(2014) 2 SCC 1"]),
        (None, ["(2015) 5 SCC 1"]),
    ]


def test_semicolons_separate_authorities():
    text = "State of Punjab v. Baldev Singh, 1999 Supp (2) SCC 101; Indra Sawhney v. Union of India, 1992 Supp (3) SCC 217."
    names = [a.case_name for a in find_authorities(text)]
    assert names == ["State of Punjab v. Baldev Singh", "Indra Sawhney v. Union of India"]


def test_two_citations_in_one_reporter_are_two_cases():
    authorities = find_authorities("(2014) 8 SCC 273, (2015) 5 SCC 1")
    assert len(authorities) == 2
