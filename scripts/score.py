"""
Score CiteCheck against the planted-error answer key.

    python scripts/score.py              # the .txt drafts
    python scripts/score.py --ext .docx  # the generated Word versions
    python scripts/score.py --ext .pdf   # the generated PDF versions
    python scripts/score.py --live       # against the real Indian Kanoon API (needs IK_API_TOKEN)

Exit code is 1 if a planted error was missed or a correct item was flagged as a problem.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from citecheck.extract import extract_file  # noqa: E402
from citecheck.kanoon import DemoKanoon, LiveKanoon  # noqa: E402
from citecheck.verify import check_text, severity  # noqa: E402

KEY = ROOT / "tests" / "answer_key.json"
DRAFTS = ROOT / "tests" / "drafts"
SAMPLES = ROOT / "samples"


def _pick_authority(results, item, used):
    for i, r in enumerate(results):
        if i in used:
            continue
        a = r.authority
        if "find" in item and a.case_name and item["find"].lower() in a.case_name.lower():
            used.add(i)
            return r
        if "find_citation" in item and any(c.raw == item["find_citation"] for c in a.citations):
            used.add(i)
            return r
    return None


def _pick_quote(results, item):
    for r in results:
        if item["find"].lower() in r.quote.text.lower():
            return r
    return None


def score(ext=".txt", backend=None):
    key = json.loads(KEY.read_text(encoding="utf-8"))
    backend = backend or DemoKanoon()
    rows = []
    for draft, expected in key.items():
        if draft.startswith("_"):
            continue
        folder = DRAFTS if ext == ".txt" else SAMPLES
        report = check_text(extract_file(folder / f"{draft}{ext}"), backend, draft)
        used = set()
        for kind, items in (("authority", expected["authorities"]), ("quote", expected["quotes"])):
            for item in items:
                r = (_pick_authority(report.authorities, item, used) if kind == "authority"
                     else _pick_quote(report.quotes, item))
                got = r.status if r else "MISSED"
                sev = severity(got) if r else "missed"
                planted = item["error"] is not None
                rows.append({
                    "draft": draft, "kind": kind, "item": item.get("find") or item.get("find_citation"),
                    "planted_error": item["error"], "expected": item["expect"], "got": got,
                    "exact": got in item["expect"],
                    "caught": planted and sev in ("problem", "check"),
                    "false_alarm": (not planted) and sev == "problem",
                    "headline": r.headline if r else "",
                })
        rows.append({"draft": draft, "kind": "_report", "calls": report.calls, "seconds": report.seconds,
                     "extra_authorities": len(report.authorities) - len(used)})
    return rows


def summarise(rows):
    items = [r for r in rows if r["kind"] != "_report"]
    planted = [r for r in items if r["planted_error"]]
    clean = [r for r in items if not r["planted_error"]]
    return {
        "items": len(items),
        "found": sum(r["got"] != "MISSED" for r in items),
        "planted": len(planted),
        "caught": sum(r["caught"] for r in planted),
        "clean": len(clean),
        "false_alarms": sum(r["false_alarm"] for r in clean),
        "exact": sum(r["exact"] for r in items),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ext", default=".txt", choices=[".txt", ".docx", ".pdf"])
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    backend = None
    if args.live:
        token = os.environ.get("IK_API_TOKEN")
        if not token:
            sys.exit("Set IK_API_TOKEN to score against the live API.")
        backend = LiveKanoon(token, ROOT / ".cache" / "kanoon")
    rows = score(args.ext, backend)
    s = summarise(rows)
    if args.json:
        print(json.dumps({"summary": s, "rows": rows}, indent=1))
    else:
        for r in rows:
            if r["kind"] == "_report":
                continue
            mark = "OK " if r["exact"] else "XX "
            print(f"{mark}{r['draft'][:22]:22} {r['kind'][:5]:5} {r['item'][:42]:42} expected {'/'.join(r['expected'])[:30]:30} got {r['got']}")
        print()
        print(f"Found by extraction : {s['found']}/{s['items']}")
        print(f"Planted errors caught: {s['caught']}/{s['planted']}")
        print(f"False alarms         : {s['false_alarms']}/{s['clean']} correct items flagged as problems")
        print(f"Exact status match   : {s['exact']}/{s['items']}")
    failed = s["caught"] < s["planted"] or s["false_alarms"] > 0
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
