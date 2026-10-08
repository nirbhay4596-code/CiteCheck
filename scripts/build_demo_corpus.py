"""
Build the offline demo corpus from saved Indian Kanoon judgment pages.

Each output file mirrors the shape of the Indian Kanoon API's /doc/ response
(tid, title, docsource, publishdate, doc), so the demo backend and the live
backend feed the verifier identical data.

Usage:
    python scripts/build_demo_corpus.py <folder of saved .html pages> citecheck/data/demo_corpus
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def judgments_div(page: str) -> str:
    """Return the inner HTML of <div class="judgments">, matched by div depth."""
    start = page.find('<div class="judgments">')
    if start < 0:
        raise ValueError("no judgments div")
    pos = start + len('<div class="judgments">')
    depth = 1
    for m in re.finditer(r"(?i)<div\b|</div>", page[pos:]):
        depth += 1 if m.group(0).lower().startswith("<div") else -1
        if depth == 0:
            return page[pos:pos + m.start()]
    raise ValueError("unbalanced judgments div")


def tidy(inner: str) -> str:
    inner = re.sub(r'(?is)<div class="covers">.*?</div>', "", inner)
    inner = re.sub(r"(?is)<a\b[^>]*>(.*?)</a>", r"\1", inner)  # keep link text, drop links
    inner = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", inner)
    return inner.strip()


def text_of(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def build(page_path: Path) -> dict:
    page = page_path.read_text(encoding="utf-8")
    inner = tidy(judgments_div(page))
    title = text_of(re.search(r'(?is)<h2 class="doc_title">(.*?)</h2>', inner).group(1))
    source = re.search(r'(?is)<h3 class="docsource_main">(.*?)</h3>', inner)
    date = re.search(r"\bon (\d{1,2} \w+, \d{4})$", title)
    return {
        "tid": int(page_path.stem),
        "title": title,
        "docsource": text_of(source.group(1)) if source else "",
        "publishdate": datetime.strptime(date.group(1), "%d %B, %Y").strftime("%Y-%m-%d") if date else "",
        "doc": inner,
        "source_url": "https://indiankanoon.org/doc/%s/" % page_path.stem,
    }


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for page_path in sorted(src.glob("*.html")):
        doc = build(page_path)
        (out / ("%d.json" % doc["tid"])).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print("%-10s %-70s %s  %6.0f KB" % (doc["tid"], doc["title"][:70], doc["publishdate"], len(doc["doc"]) / 1024))


if __name__ == "__main__":
    main()
