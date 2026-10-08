"""
Find quoted passages in a draft and check them against the judgment's text.

A quote passes only if every word matches; punctuation, capitals and line
breaks are ignored. Lawyers' editing conventions are respected: an ellipsis
(...) or a bracketed insertion ([the police]) splits the quote into pieces,
and each piece is checked on its own.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .citations import SUPRA, Authority
from .kanoon import Doc
from .names import MATCH_THRESHOLD, name_score

MIN_WORDS = 8
_QUOTE = re.compile(r"[“\"]([^“”\"]{30,2500}?)[”\"]", re.S)
_PINPOINT = re.compile(r"\b(?:para(?:graph)?s?|¶)\.?\s*(\d+(?:\s*(?:-|–|to|and|&|,)\s*\d+)*)", re.IGNORECASE)
_SPLIT = re.compile(r"\s*(?:\.\s?\.\s?\.|…|\[[^\]]{0,80}\])\s*")


@dataclass
class Quote:
    text: str
    start: int
    end: int
    authority_id: int | None = None
    pinpoint: str | None = None


def _attribute(text: str, start: int, end: int, authorities: list[Authority],
               supra: list[tuple[int, int]]) -> int | None:
    mentions = [(a.start, a.id) for a in authorities] + supra
    before = [m for m in mentions if m[0] < start and start - m[0] < 1500]
    if before:
        return max(before)[1]
    after = [m for m in mentions if m[0] > end and m[0] - end < 250]
    return min(after)[1] if after else None


def find_quotes(text: str, authorities: list[Authority]) -> list[Quote]:
    supra = []
    for m in SUPRA.finditer(text):
        best = max(((name_score(m.group(1), a.case_name or ""), a.id) for a in authorities if a.case_name),
                   default=(0, None))
        if best[0] >= MATCH_THRESHOLD - 10:
            supra.append((m.start(), best[1]))
    quotes = []
    for m in _QUOTE.finditer(text):
        body = re.sub(r"\s+", " ", m.group(1)).strip()
        if len(body.split()) < MIN_WORDS:
            continue
        around = text[max(0, m.start() - 120):m.start()] + " " + text[m.end():m.end() + 120]
        pin = _PINPOINT.search(around)
        quotes.append(Quote(body, m.start(), m.end(),
                            _attribute(text, m.start(), m.end(), authorities, supra),
                            pin.group(1) if pin else None))
    return quotes


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------

def _norm_words(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s).lower().replace("�", " ")
    return re.findall(r"[a-z0-9]+", s)


@dataclass
class Located:
    score: float                  # 0-100
    anchor: str                   # paragraph anchor in the judgment, e.g. "p_12"
    found_words: list[str]        # the judgment's words, as aligned
    changes: list[tuple[str, str]] = field(default_factory=list)  # (draft says, judgment says)

    @property
    def exact(self) -> bool:
        return not self.changes


class Judgment:
    """A judgment's text prepared for repeated quote lookups."""

    def __init__(self, doc: Doc):
        self.doc = doc
        self.words: list[str] = []
        self.anchor_at: list[str] = []  # anchor for each word
        for anchor, para in doc.paragraphs():
            ws = _norm_words(para)
            self.words += ws
            self.anchor_at += [anchor] * len(ws)
        self.joined = " ".join(self.words)
        # character offset of each word in self.joined
        self.offsets, pos = [], 0
        for w in self.words:
            self.offsets.append(pos)
            pos += len(w) + 1

    def _word_index(self, char_pos: int) -> int:
        lo, hi = 0, len(self.offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.offsets[mid] <= char_pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def locate_piece(self, piece: str) -> Located | None:
        q = _norm_words(piece)
        if not q or not self.words:
            return None
        needle = " ".join(q)
        padded = f" {self.joined} "
        hits, pos = [], padded.find(f" {needle} ")  # whole words only
        while pos >= 0:
            hits.append(self._word_index(pos))
            pos = padded.find(f" {needle} ", pos + 1)
        if hits:
            # prefer the Court's own paragraphs over a reporter's headnote (<pre> blocks)
            i = next((h for h in hits if not self.anchor_at[h].startswith("pre_")), hits[0])
            return Located(100.0, self.anchor_at[i], self.words[i:i + len(q)])
        al = fuzz.partial_ratio_alignment(needle, self.joined, score_cutoff=60)
        if al is None:
            return None
        i0 = self._word_index(al.dest_start)
        i1 = self._word_index(max(al.dest_start, al.dest_end - 1)) + 1
        found = self.words[i0:i1]
        changes = []
        for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, q, found, autojunk=False).get_opcodes():
            if op != "equal":
                changes.append((" ".join(q[a0:a1]), " ".join(found[b0:b1])))
        # trim edits that are only the aligner overshooting at either end
        while changes and changes[0][0] == "" and found[:len(changes[0][1].split())] == changes[0][1].split():
            changes.pop(0)
        while changes and changes[-1][0] == "" and found[-len(changes[-1][1].split()):] == changes[-1][1].split():
            changes.pop()
        return Located(al.score, self.anchor_at[i0], found, changes)

    def locate(self, quote: str) -> Located | None:
        pieces = [p for p in _SPLIT.split(quote) if len(_norm_words(p)) >= 4] or [quote]
        found = [self.locate_piece(p) for p in pieces]
        if any(f is None for f in found):
            return None
        return Located(min(f.score for f in found), found[0].anchor,
                       [w for f in found for w in f.found_words],
                       [c for f in found for c in f.changes])
