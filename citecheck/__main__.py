"""
Command line:

    python -m citecheck path/to/draft.pdf            # live, needs IK_API_TOKEN
    python -m citecheck path/to/draft.docx --demo    # offline demo library, free
    python -m citecheck draft.pdf --csv report.csv
"""

import argparse
import os
import sys

from .extract import UnsupportedFile, extract_file
from .kanoon import DemoKanoon, LiveKanoon
from .report import to_csv, to_markdown
from .verify import check_text


def main():
    ap = argparse.ArgumentParser(prog="citecheck", description="Check case citations and quotations in a draft.")
    ap.add_argument("draft")
    ap.add_argument("--demo", action="store_true", help="use the offline demo library instead of the live API")
    ap.add_argument("--csv", metavar="FILE", help="also write the results to a CSV file")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("CITECHECK_DAILY_CALL_LIMIT", 100)),
                    help="maximum Indian Kanoon calls per day (default 100)")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.demo:
        backend = DemoKanoon()
    else:
        token = os.environ.get("IK_API_TOKEN")
        if not token:
            sys.exit("Set IK_API_TOKEN to your Indian Kanoon API token, or use --demo.")
        backend = LiveKanoon(token, daily_call_limit=args.limit)
    try:
        text = extract_file(args.draft)
    except (UnsupportedFile, OSError) as exc:
        sys.exit(str(exc))
    report = check_text(text, backend, os.path.basename(args.draft))
    print(to_markdown(report))
    if not args.demo:
        print(f"\nIndian Kanoon calls: {report.calls}  (≈ ₹{report.cost_inr:.2f})")
    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(to_csv(report))


if __name__ == "__main__":
    main()
