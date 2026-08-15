#!/usr/bin/env python3
"""python scripts/build_overview_pdf.py

Renders docs/launch/aegis-overview.html to docs/launch/aegis-overview.pdf
with headless Chromium, the same browser the e2e suite and the demo
recorder already provision.

Chromium rather than reportlab on purpose. The evidence pack
(aegis/evidence_pack.py) builds its PDF from reportlab primitives because
it is generated per incident at runtime from database rows. This one is a
two-page document whose layout is the point, and CSS is a better tool for
that than hand-placed flowables.

Every number in the HTML traces to a run recorded in the repo: the 7s heal
and 13s detection from the demo capture, 93/53/9 from `make test`, 18/19
from `MOCK_LLM=1 make e2e`, and the live table from PHASE_6_REPORT.md with
its model set named next to it.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "docs" / "launch" / "aegis-overview.html"
OUTPUT = REPO_ROOT / "docs" / "launch" / "aegis-overview.pdf"


def main() -> int:
    if not SOURCE.exists():
        print(f"missing {SOURCE}", file=sys.stderr)
        return 1

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(SOURCE.as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(OUTPUT),
                format="A4",
                # The page's own @page margins do the spacing; asking
                # Chromium for margins too would double them.
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            browser.close()

    print(f"{OUTPUT.relative_to(REPO_ROOT)}  {OUTPUT.stat().st_size / 1000:.0f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
