"""The web page runs, and Indian Kanoon's required attribution sits on top of every set of results."""

from streamlit.testing.v1 import AppTest

from citecheck.kanoon import DemoKanoon
from citecheck.report import ATTRIBUTION, to_csv, to_markdown
from citecheck.verify import check_text


def test_sample_runs_with_attribution_above_results():
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    at.button(key="run_sample").click().run()
    assert not at.exception
    markdown = [m.value for m in at.markdown]
    logo_at = next(i for i, m in enumerate(markdown) if "ikanoon6_powered_transparent.png" in m)
    first_result_at = next(i for i, m in enumerate(markdown) if "Arnesh Kumar" in m)
    assert logo_at < first_result_at, "the 'powered by' graphic must come before the results"
    assert 'width="150"' in markdown[logo_at], "the graphic must be shown at its natural size"


def test_downloads_carry_attribution():
    report = check_text("Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273", DemoKanoon(), "x.txt")
    assert ATTRIBUTION in to_markdown(report)
    assert to_csv(report).splitlines()[0].strip('"') == ATTRIBUTION
