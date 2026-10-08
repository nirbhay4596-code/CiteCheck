"""End to end: every planted error caught, no correct item flagged, in every file format."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from score import score, summarise  # noqa: E402


@pytest.mark.parametrize("ext", [".txt", ".docx", ".pdf"])
def test_answer_key(ext):
    s = summarise(score(ext))
    assert s["found"] == s["items"], "extraction missed an item"
    assert s["caught"] == s["planted"], "a planted error got through"
    assert s["false_alarms"] == 0, "a correct item was flagged as a problem"
    assert s["exact"] == s["items"]
