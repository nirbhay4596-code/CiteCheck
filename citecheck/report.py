"""Turn a Report into rows (for tables and CSV) and Markdown (for the command line and downloads)."""

import csv
import io

from .verify import Report, label

ICON = {"ok": "✅", "check": "🟡", "problem": "❌"}
# Indian Kanoon's API terms require clear attribution wherever results are shown
ATTRIBUTION = ("Powered by Indian Kanoon (https://indiankanoon.org). CiteCheck is an independent tool and is "
               "not affiliated with or endorsed by Indian Kanoon.")


def _changes(changes) -> str:
    parts = []
    for draft, judgment in changes:
        if draft and judgment:
            parts.append(f"draft says “{draft}”, judgment says “{judgment}”")
        elif judgment:
            parts.append(f"draft leaves out “{judgment}”")
        else:
            parts.append(f"draft adds “{draft}”")
    return "; ".join(parts)


def authority_rows(report: Report) -> list[dict]:
    rows = []
    for r in report.authorities:
        rows.append({
            "#": r.authority.id,
            "Result": f"{ICON[r.severity]} {label(r.status)}",
            "Authority in the draft": r.authority.label,
            "What we found": r.headline,
            "Correct citation": r.suggestion or "",
            "Link": r.match.url if r.match else "",
        })
    return rows


def quote_rows(report: Report) -> list[dict]:
    rows = []
    for i, r in enumerate(report.quotes, 1):
        text = r.quote.text
        rows.append({
            "#": i,
            "Result": f"{ICON[r.severity]} {label(r.status)}",
            "Quotation": text if len(text) < 160 else text[:157] + "…",
            "Attributed to": r.authority_label or "",
            "What we found": r.headline + (f" ({_changes(r.changes)})" if r.changes else ""),
            "Link": r.url or "",
        })
    return rows


def to_csv(report: Report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([ATTRIBUTION])
    w.writerow(["Type", "#", "Result", "Item", "Attributed to", "What we found", "Correct citation", "Link"])
    for r in authority_rows(report):
        w.writerow(["Authority", r["#"], r["Result"], r["Authority in the draft"], "", r["What we found"],
                    r["Correct citation"], r["Link"]])
    for r in quote_rows(report):
        w.writerow(["Quotation", r["#"], r["Result"], r["Quotation"], r["Attributed to"], r["What we found"],
                    "", r["Link"]])
    return buf.getvalue()


def to_markdown(report: Report) -> str:
    out = [f"# Citation check: {report.filename or 'draft'}", "", f"_{ATTRIBUTION}_", ""]
    out.append(f"Checked against: {report.backend}. "
               f"{len(report.authorities)} authorities, {len(report.quotes)} quotations. "
               f"{report.count('problem')} problems, {report.count('check')} to check by hand.")
    out.append("")
    for e in report.errors:
        out.append(f"> ⚠️ {e}")
    out += ["", "## Authorities", ""]
    for r in authority_rows(report):
        out.append(f"{r['#']}. {r['Result']} — **{r['Authority in the draft']}**  ")
        out.append(f"   {r['What we found']}" + (f" [Open]({r['Link']})" if r["Link"] else ""))
    if report.quotes:
        out += ["", "## Quotations", ""]
        for r in quote_rows(report):
            out.append(f"{r['#']}. {r['Result']} — “{r['Quotation']}”  ")
            out.append(f"   {r['What we found']}" + (f" [Open]({r['Link']})" if r["Link"] else ""))
    out += ["", "_CiteCheck checks citations against Indian Kanoon. It does not replace reading the authority._"]
    return "\n".join(out)
