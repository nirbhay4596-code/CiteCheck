"""
CiteCheck web app.

    streamlit run app.py

Samples run on the offline demo library and cost nothing. Uploads use the live
Indian Kanoon API when IK_API_TOKEN is set (environment variable or Streamlit secret).
"""

import os
from pathlib import Path

import streamlit as st

from citecheck.extract import UnsupportedFile, extract_text
from citecheck.kanoon import COST_INR, DemoKanoon, LiveKanoon
from citecheck.report import ICON, to_csv, to_markdown
from citecheck.verify import Report, label, severity

ROOT = Path(__file__).parent
SAMPLES = {
    "Anticipatory bail, written submissions (Saket Courts)": "draft_a_anticipatory_bail",
    "Sexual harassment writ, note of arguments (Delhi High Court)": "draft_b_posh_writ",
    "Online speech and illegal arrest, written submissions (Bombay High Court)": "draft_c_online_speech",
}
DAILY_LIMIT = int(os.environ.get("CITECHECK_DAILY_CALL_LIMIT", 100))
# Indian Kanoon's API terms require their "powered by" graphic on top of results, full size and unaltered.
# It is loaded from their server rather than copied, so it is always their current, official version.
IK_LOGO_URL = "https://api.indiankanoon.org/static/pics/ikanoon6_powered_transparent.png"
IK_LOGO_WIDTH = 150  # the graphic's natural width: never resize it

st.set_page_config(page_title="CiteCheck: citation checker for Indian court filings", page_icon="⚖️",
                   layout="wide")


def ik_token() -> str | None:
    token = os.environ.get("IK_API_TOKEN")
    if token:
        return token
    try:
        return st.secrets.get("IK_API_TOKEN")
    except Exception:  # no secrets file configured
        return None


@st.cache_resource
def demo_backend() -> DemoKanoon:
    return DemoKanoon()


@st.cache_resource
def live_backend(token: str) -> LiveKanoon:
    return LiveKanoon(token, ROOT / ".cache" / "kanoon", daily_call_limit=DAILY_LIMIT)


def run(text: str, backend, filename: str) -> Report:
    from citecheck.verify import check_text

    before = dict(backend.calls)
    report = check_text(text, backend, filename)
    report.calls = {k: backend.calls[k] - before.get(k, 0) for k in backend.calls}
    live = report.backend.startswith("Indian Kanoon")
    report.cost_inr = sum(COST_INR[k] * report.calls.get(k, 0) for k in COST_INR) if live else 0.0
    return report


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------

def changes_md(changes) -> str:
    parts = []
    for draft, judgment in changes:
        if draft and judgment:
            parts.append(f"draft says **“{draft}”**, judgment says **“{judgment}”**")
        elif judgment:
            parts.append(f"draft leaves out **“{judgment}”**")
        else:
            parts.append(f"draft adds **“{draft}”**")
    return "; ".join(parts)


def card(status: str, title: str, body: str, link: str | None, extra: str | None = None):
    with st.container(border=True):
        left, right = st.columns([1, 4], vertical_alignment="top")
        sev = severity(status)
        colour = {"ok": "green", "check": "orange", "problem": "red"}[sev]
        left.markdown(f"{ICON[sev]} :{colour}[**{label(status)}**]")
        right.markdown(title)
        right.markdown(body)
        if extra:
            right.markdown(extra)
        if link:
            right.markdown(f"[Open on Indian Kanoon ↗]({link})")


def attribution():
    logo, note = st.columns([1, 5], vertical_alignment="center")
    logo.markdown(f'<a href="https://indiankanoon.org" target="_blank">'
                  f'<img src="{IK_LOGO_URL}" width="{IK_LOGO_WIDTH}" alt="powered by IKanoon"></a>',
                  unsafe_allow_html=True)
    note.caption("Case law and judgment text from [Indian Kanoon](https://indiankanoon.org). CiteCheck is an "
                 "independent tool and is not affiliated with or endorsed by Indian Kanoon.")


def render(report: Report):
    attribution()
    problems, checks = report.count("problem"), report.count("check")
    ok = report.count("ok")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Authorities", len(report.authorities))
    c2.metric("Quotations", len(report.quotes))
    c3.metric("❌ Problems", problems)
    c4.metric("🟡 Check by hand", checks)
    for e in report.errors:
        st.warning(e)
    if problems == 0 and checks == 0 and ok:
        st.success("Every authority and quotation checked out.")

    only_issues = st.toggle("Show only items that need attention", value=False)

    st.subheader("Authorities")
    if not report.authorities:
        st.info("No case citations found. CiteCheck recognises SCC, SCC OnLine, AIR, SCR, INSC, SCALE, JT, "
                "MANU, Cri LJ and DLT citations.")
    for r in report.authorities:
        if only_issues and r.severity == "ok":
            continue
        extra = f"Correct citation: **{r.suggestion}**" if r.suggestion else None
        card(r.status, f"**{r.authority.label}**", r.headline, r.match.url if r.match else None, extra)

    if report.quotes:
        st.subheader("Quotations")
        for r in report.quotes:
            if only_issues and r.severity == "ok":
                continue
            attributed = f"  \n_Attributed to {r.authority_label}_" if r.authority_label else ""
            extra = changes_md(r.changes) if r.changes else None
            card(r.status, f"“{r.quote.text}”{attributed}", r.headline, r.url, extra)

    d1, d2, _ = st.columns([1, 1, 3])
    stem = Path(report.filename or "draft").stem
    d1.download_button("Download report (.md)", to_markdown(report), f"{stem}-citecheck.md", "text/markdown")
    d2.download_button("Download table (.csv)", to_csv(report), f"{stem}-citecheck.csv", "text/csv")
    paid = sum(v for k, v in report.calls.items() if k != "cached")
    cost = (f" · {paid} Indian Kanoon calls, ≈ ₹{report.cost_inr:.2f} ({report.calls.get('cached', 0)} answered "
            "free from the cache)") if report.backend.startswith("Indian Kanoon") else " · no cost"
    st.caption(f"Checked against {report.backend} in {report.seconds:.1f}s{cost}.")


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------

st.title("CiteCheck")
st.markdown("##### Checks every case citation and quotation in a draft against Indian Kanoon, before you file.")

with st.expander("How it works, and what it won't claim"):
    st.markdown("""
- **Finds** every citation in the draft (SCC, AIR, SCR, SCC OnLine, INSC, SCALE, JT, MANU and more), the case name
  in front of it, and every quotation of eight words or more.
- **Checks** each one on Indian Kanoon: does the case exist, is it reported at that volume and page, and does the
  quoted passage appear in the judgment word for word? If a quote is real but from a different case, it says which.
- **No AI.** Citations are found by pattern matching and checked against the source. The tool can't make up a case.
- **Honest about gaps.** Indian Kanoon doesn't list every reporter for every case. When it can't confirm a volume and
  page, CiteCheck says *couldn't confirm*, never *wrong*.
- **Private.** Your draft is read in memory and not stored. Only citations and case names go to Indian Kanoon.
""")

samples_tab, upload_tab = st.tabs(["Try a sample", "Check your draft"])

with samples_tab:
    st.markdown("Three mock filings with nine planted mistakes between them: invented cases, a wrong year, a wrong "
                "volume, a real citation under a made-up name, altered and misattributed quotations.")
    # ?sample=a|b|c opens the page with that sample already checked: handy for sharing a link
    linked = {"a": 0, "b": 1, "c": 2}.get(st.query_params.get("sample", ""))
    choice = st.selectbox("Sample draft", list(SAMPLES), index=linked or 0)
    stem = SAMPLES[choice]
    sample_pdf = ROOT / "samples" / f"{stem}.pdf"
    a, b, _ = st.columns([1, 1, 3])
    go = a.button("Check this draft", type="primary", key="run_sample")
    if linked is not None and "sample_report" not in st.session_state:
        go = True
    b.download_button("See the draft (PDF)", sample_pdf.read_bytes(), sample_pdf.name, "application/pdf")
    if go:
        st.session_state["sample_report"] = run(
            extract_text(sample_pdf.read_bytes(), sample_pdf.name), demo_backend(), sample_pdf.name)
    if st.session_state.get("sample_report") and st.session_state["sample_report"].filename == sample_pdf.name:
        render(st.session_state["sample_report"])

with upload_tab:
    token = ik_token()
    if not token:
        st.info("Live checks need an Indian Kanoon API token, so this public demo runs on the samples only. "
                "To check your own drafts, run CiteCheck on your computer with your own token: see the README.")
    else:
        backend = live_backend(token)
        left = max(0, DAILY_LIMIT - backend.calls_today())
        st.caption(f"{left} of {DAILY_LIMIT} Indian Kanoon lookups left today. A typical draft uses 10 to 30.")
        uploaded = st.file_uploader("Upload a draft", type=["pdf", "docx", "txt"])
        pasted = st.text_area("…or paste the text", height=150)
        if st.button("Check citations", type="primary", disabled=not (uploaded or pasted.strip()) or left == 0):
            try:
                if uploaded:
                    text, name = extract_text(uploaded.getvalue(), uploaded.name), uploaded.name
                else:
                    text, name = pasted, "pasted text"
                with st.spinner("Checking against Indian Kanoon…"):
                    st.session_state["live_report"] = run(text, backend, name)
            except UnsupportedFile as exc:
                st.error(str(exc))
        if st.session_state.get("live_report"):
            render(st.session_state["live_report"])

st.divider()
st.caption("CiteCheck is a checking aid. It does not replace reading the authority. "
           "Judgment text from [Indian Kanoon](https://indiankanoon.org); CiteCheck is not affiliated with or "
           "endorsed by Indian Kanoon.")
