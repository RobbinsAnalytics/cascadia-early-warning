"""Render the page and every chart across the K6 width ladder.

CHART-REVIEW K6: the review is run at the narrowest width, the design width,
and the two viewports either side of every declared breakpoint CROSSING,
measured on the chart element's width rather than the window's. The ladder is
derived from `window.CASCADIA_BREAKPOINTS`, declared once in
docs/assets/page.js; the mechanism is the one worked at
cascadia-matter-ledger-analytics/src/render_charts.py.

Also checked at every width: horizontal overflow (Rule 5.3's WCAG 1.4.10
clause), the rendered provenance segment count (K5), the real ECharts grid
rect, and console errors. The page is served at http://localhost:8731/ by
`python -m http.server 8731 --directory docs` (see .claude/launch.json), so
the renders are a behaviour check of the page a reader would load, not of a
data: snapshot.

Output: docs/renders/<chart>-<width>.png plus page-<width>.png, and
docs/renders/k6-ladder.json with the widths and crossings. Exit non-zero if
any width overflows horizontally or a chart fails to draw.

    python src/render_charts.py            # the K6 ladder
    python src/render_charts.py 390 768    # explicit widths
"""
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "renders"
URL = "http://localhost:8731/"
DESIGN_WIDTH = 1040
NARROW_WIDTH = 320
SEARCH_MAX = 1600
CHARTS = ["c1", "c2", "c3", "c4", "c5"]


def k6_ladder(browser):
    page = browser.new_page(viewport={"width": DESIGN_WIDTH, "height": 900})
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(600)
    bps = page.evaluate("() => window.CASCADIA_BREAKPOINTS || null")
    if not bps:
        page.close()
        sys.exit("page.js declares no window.CASCADIA_BREAKPOINTS; failing closed rather than typing a ladder")

    def host_width(viewport, cid):
        page.set_viewport_size({"width": viewport, "height": 900})
        page.wait_for_timeout(60)
        return page.evaluate("(id) => document.getElementById(id).clientWidth", cid)

    widths = {NARROW_WIDTH, DESIGN_WIDTH}
    crossings = []
    for cid in CHARTS:
        for b in bps:
            lo, hi = NARROW_WIDTH, SEARCH_MAX
            if host_width(hi, cid) < b:
                continue
            if host_width(lo, cid) >= b:
                continue
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if host_width(mid, cid) >= b:
                    hi = mid
                else:
                    lo = mid
            crossings.append((cid, b, hi))
            widths.add(lo)
            widths.add(hi)
    page.close()
    return sorted(widths), list(bps), crossings


def main():
    argv = sys.argv[1:]
    out_dir = OUT
    if "--out" in argv:
        i = argv.index("--out")
        out_dir = pathlib.Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    widths = [int(a) for a in argv if a.isdigit()]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is required")
    out_dir.mkdir(parents=True, exist_ok=True)
    overflow_failures, draw_failures = [], []
    record = {"url": URL, "widths": [], "breakpoints": [], "crossings": [], "per_width": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        if widths:
            print("explicit widths: %s" % ", ".join(str(w) for w in widths))
            bps, crossings = [], []
        else:
            widths, bps, crossings = k6_ladder(browser)
            print("K6 ladder derived from declared breakpoints %s" % ", ".join(str(b) for b in bps))
            for cid, b, v in crossings:
                print("  %s crosses host %d px between viewport %d and %d" % (cid, b, v - 1, v))
            print("  widths: %s" % ", ".join(str(w) for w in widths))
        record["widths"], record["breakpoints"] = widths, bps
        record["crossings"] = [{"chart": c, "breakpoint": b, "viewport": v} for c, b, v in crossings]
        for width in widths:
            page = browser.new_page(viewport={"width": width, "height": 1400}, device_scale_factor=2)
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(URL, wait_until="networkidle")
            page.wait_for_timeout(1500)
            if errors:
                print("  CONSOLE ERRORS at %dpx:" % width)
                for e in errors[:8]:
                    print("    " + e)
            page.screenshot(path=str(out_dir / ("page-%d.png" % width)), full_page=True)
            for cid in CHARTS:
                card = page.locator("#card-" + cid)
                target = card if card.count() else page.locator("#" + cid)
                # A card taller than the viewport is scrolled to its centre for the capture, which slid it
                # under the sticky site header (c4 at 320 px). The header is made static for the shot only;
                # the page a reader loads is unchanged.
                target.screenshot(path=str(out_dir / ("%s-%d.png" % (cid, width))),
                                  style="#site-header{position:static !important}")
            seg = page.evaluate(
                """() => Array.from(document.querySelectorAll('.cascadia-provenance'))
                        .map(n => n.textContent.split(' \\u00b7 ').length)""")
            dims = page.evaluate(
                """() => Object.fromEntries(['c1','c2','c3','c4','c5'].map(id => {
                     const cv = document.getElementById(id).querySelector('canvas');
                     return [id, cv ? cv.width + 'x' + cv.height : 'none'];
                   }))""")
            grid = page.evaluate(
                """() => Object.fromEntries(['c1','c2','c3','c4','c5'].map(id => {
                     try {
                       const ch = echarts.getInstanceByDom(document.getElementById(id));
                       const g = ch.getModel().getComponent('grid').coordinateSystem.getRect();
                       return [id, Math.round(g.width)];
                     } catch (e) { return [id, 'n/a']; }
                   }))""")
            over = page.evaluate(
                """() => ({scroll: document.documentElement.scrollWidth,
                          client: document.documentElement.clientWidth})""")
            print("  width %d: strip segments %s" % (width, seg))
            print("  width %d: canvas %s" % (width, dims))
            print("  width %d: grid px %s" % (width, grid))
            for cid, v in dims.items():
                if v == "none":
                    draw_failures.append((width, cid))
            if over["scroll"] > over["client"] + 1:
                overflow_failures.append((width, over["scroll"], over["client"]))
                print("  width %d: HORIZONTAL OVERFLOW scrollWidth %d > clientWidth %d" % (width, over["scroll"], over["client"]))
            record["per_width"][str(width)] = {"strip_segments": seg, "canvas": dims, "grid_px": grid,
                                               "overflow": over, "console_errors": errors[:8]}
            page.close()
        browser.close()

    (out_dir / "k6-ladder.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("\nrenders in %s" % out_dir)
    if draw_failures:
        print("\nCHARTS DID NOT DRAW: %s" % draw_failures)
        sys.exit(1)
    if overflow_failures:
        print("\nRULE 5.3 / WCAG 1.4.10 FAILED, the page scrolls sideways:")
        for w, sw, cw in overflow_failures:
            print("  at %d px the document is %d px wide (over by %d)" % (w, sw, sw - cw))
        sys.exit(1)


if __name__ == "__main__":
    main()
