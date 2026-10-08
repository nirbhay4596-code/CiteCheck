"""
Capture README screenshots of the running app (dev only: pip install playwright).

    streamlit run app.py --server.port 8765   # in another terminal
    python scripts/screenshots.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs"
URL = "http://localhost:8765/?sample={}"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")  # uses the installed Chrome, no download
    for sample in "abc":
        page = browser.new_page(viewport={"width": 1100, "height": 3600}, device_scale_factor=1.5)
        page.goto(URL.format(sample))
        page.get_by_text("Download report (.md)").wait_for(timeout=30000)
        page.wait_for_timeout(800)
        footer = page.get_by_text("CiteCheck is a checking aid").bounding_box()
        page.screenshot(path=OUT / f"screenshot-sample-{sample}.png",
                        clip={"x": 0, "y": 0, "width": 1100, "height": footer["y"] + footer["height"] + 40})
        print("saved sample", sample)
    browser.close()
