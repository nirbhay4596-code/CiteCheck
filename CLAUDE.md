# CiteCheck: notes for development sessions

Citation checker for Indian court filings. It finds every case citation and quotation in a draft (PDF, DOCX or text) and checks each one against Indian Kanoon. Streamlit web app (`app.py`) plus a command line (`python -m citecheck`).

## Commands

```bash
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                   # 50 tests, all must pass
python scripts/score.py --ext .pdf       # planted-error scorecard (also .txt, .docx)
python scripts/score.py --live           # same drafts against the real API; needs IK_API_TOKEN
streamlit run app.py                     # web app; samples work offline
python scripts/make_samples.py           # rebuild samples/*.docx|pdf from tests/drafts/*.txt
python scripts/screenshots.py            # README screenshots; app must be running on port 8765
```

## Layout

- `citecheck/citations.py`: citation patterns, canonical keys, case names, parallel citations
- `citecheck/names.py`: party-by-party case-name matching (word level; "Ramesh" must not match "Rajesh")
- `citecheck/kanoon.py`: `LiveKanoon` (cached, daily call limit) and `DemoKanoon` (offline corpus), same interface
- `citecheck/quotes.py`: quotation finding, exact match, close match with word-level diff
- `citecheck/verify.py`: decides each status; `STATUSES` holds labels and severities
- `citecheck/report.py`: table rows, Markdown and CSV, including the Indian Kanoon attribution
- `tests/drafts/` and `tests/answer_key.json`: 3 mock filings, 9 planted errors, 16 correct items
- `citecheck/data/demo_corpus/`: 6 Supreme Court judgments saved from public Indian Kanoon pages

## Rules that must hold

1. **No generative AI in the checking path.** Findings come from pattern matching and comparison with the source text.
2. **Say only what the source supports.** If Indian Kanoon doesn't list the cited reporter, the status is "couldn't confirm" (`CASE_FOUND`), never "wrong". If several cases share a name and none matches, the status is `NEEDS_REVIEW`; don't guess.
3. **Indian Kanoon attribution is mandatory** under their API terms: the official "powered by" graphic on top of every set of results, at its natural 150px width, never altered, plus a not-affiliated line. `tests/test_app.py` guards this.
4. **Blind tests are scored before any tuning.** When new test drafts arrive, run and record the score first, then fix. Never adjust code to a blind set before scoring it.
5. **Keep the cost at zero.** Cache every API response; respect `CITECHECK_DAILY_CALL_LIMIT`.

## Status

Done: engine, web app, CLI, 50 tests, scorecard 25/25 in txt/docx/pdf, README, deploy guide,
grant-request draft, deployed at https://citecheck.streamlit.app, first live Indian Kanoon run
(9 Oct 2026: 9/9 planted errors caught, 0 false alarms, 22/25 exact — see `docs/live-run-2026-10-09.md`).

Not yet done:
- Fix the one real gap the live run found: in `verify.py`, `_found_case` settles on `CASE_FOUND`
  when a name candidate exists but isn't tied to the cited citation, even when Indian Kanoon
  lists that citation as another case's own. That should be `NAME_MISMATCH` — it is the
  fabricated-name case, and saying so is source-supported, not guessing. Details in
  `docs/live-run-2026-10-09.md`.
- Give `tests/answer_key.json` per-backend expectations. Two of its statuses encode what the
  6-document demo corpus can support, not what the real corpus supports, so `--live` cannot
  reach 25/25 until the key distinguishes them.
- Blind test drafts written by someone who hasn't seen the code.

Known limitations are listed in the README.
