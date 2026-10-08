"""
Compare a case name as written in a draft with a title on Indian Kanoon.

Drafts and Indian Kanoon spell parties differently ("Union of India" vs
"U.O.I", "Govt. of U.P." vs "Government of Uttar Pradesh", "& Anr." or not),
so names are normalised first and then compared side by side: petitioner with
petitioner, respondent with respondent.
"""

import re

from rapidfuzz import fuzz

MATCH_THRESHOLD = 85

_V_SPLIT = re.compile(r"\s(?:v|vs|v/s|versus)\.?\s", re.IGNORECASE)
_DATE_SUFFIX = re.compile(r"\s+on\s+\d{1,2}\s+\w+,?\s+\d{4}\s*$", re.IGNORECASE)

_EXPANSIONS = [
    (r"\bu o i\b|\buoi\b", "union india"),
    (r"\bgovt\b|\bgovernment\b", "government"),
    (r"\bu p\b", "uttar pradesh"),
    (r"\bm p\b", "madhya pradesh"),
    (r"\bw b\b", "west bengal"),
    (r"\bh p\b", "himachal pradesh"),
    (r"\ba p\b", "andhra pradesh"),
    (r"\bt n\b", "tamil nadu"),
    (r"\bj k\b|\bj and k\b", "jammu kashmir"),
    (r"\bnct\b", "nct"),
    (r"\bcorpn\b", "corporation"),
]

_NOISE = {
    "the", "of", "and", "anr", "ors", "others", "another", "etc", "shri", "sri", "smt", "dr", "mr", "mrs",
    "ms", "m", "s", "retd", "dead", "lrs", "thr", "through", "by", "rep", "represented", "its", "pvt", "ltd",
    "limited", "co", "in", "re",
}


def _normalise(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = " " + " ".join(re.sub(r"[^a-z0-9]+", " ", s).split()) + " "
    for pattern, repl in _EXPANSIONS:
        s = re.sub(pattern, repl, s)
    return " ".join(w for w in s.split() if w not in _NOISE)


def split_parties(name: str) -> tuple[str, str]:
    name = _DATE_SUFFIX.sub("", name or "")
    parts = _V_SPLIT.split(f" {name} ", maxsplit=1)
    if len(parts) == 2:
        return _normalise(parts[0]), _normalise(parts[1])
    return _normalise(name), ""


def _word_match(a: str, b: str) -> float:
    if a == b:
        return 1.0
    # spelling variants (Vishaka / Vishakha) only for longer words: Ramesh is not Rajesh
    if min(len(a), len(b)) >= 6 and fuzz.ratio(a, b) >= 88:
        return 0.9
    return 0.0


def _coverage(words: list[str], other: list[str]) -> float:
    if not words or not other:
        return 0.0
    return sum(max(_word_match(w, o) for o in other) for w in words) / len(words)


def _party_score(d: str, t: str) -> float:
    dw, tw = d.split(), t.split()
    # either side may be the shortened one ("D.K. Basu" vs "D.K. Basu, Ashok K. Johri")
    return 100 * max(_coverage(dw, tw), _coverage(tw, dw))


def name_score(draft_name: str, title: str) -> int:
    """0-100: how confidently the draft's case name and an Indian Kanoon title name the same case."""
    d_pet, d_resp = split_parties(draft_name)
    t_pet, t_resp = split_parties(title)
    if not d_pet or not t_pet:
        return 0
    pet = _party_score(d_pet, t_pet)
    # a one-word petitioner ("Sharma") contained in a longer one ("Rajesh Sharma") proves little
    if len(d_pet.split()) == 1 and len(t_pet.split()) > 1:
        pet -= 15
    if d_resp and t_resp:
        return round(0.7 * pet + 0.3 * _party_score(d_resp, t_resp))
    return round(pet)


def name_query(draft_name: str) -> str:
    """Plain-words search query for a case name."""
    pet, resp = split_parties(draft_name)
    return " ".join((pet + " " + resp).split()[:10])


def short_title(title: str) -> str:
    return _DATE_SUFFIX.sub("", title or "").strip()
