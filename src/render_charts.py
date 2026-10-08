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
    python src/render_charts.py --page case-study.html --charts c3
                                           # a second page: its own K6 ladder, its own
                                           # chart list, renders under docs/renders/case-study/
    python src/render_charts.py --tables tbl-outlook,tbl-scores,tbl-c4
                                           # also each named table, its details opened, as
                                           # table-<id>-<width>.png at 320 and 1040 only
    python src/render_charts.py --page case-study.html --charts c3 --card
                                           # also the case study's card as card-<width>.png,
                                           # at 320 and 1040 only (Build Brief 2.2 step 10)
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


def dialog_check(page, tid, width, out_dir):
    """Open table tid full screen through its own control, check it and close it with Esc. Returns a failure or ''."""
    btn = page.locator('button[data-expand="%s"]' % tid)
    if not btn.count():
        return "no expand control"
    page.evaluate("(id) => { const d = document.querySelector('[data-table-block=\"' + id + '\"]').closest('details'); if (d) d.open = true; }", tid)
    # The inline table first: scrolled sideways, its first column stays where it was.
    inline = page.evaluate("""(id) => { const w = document.querySelector('[data-scroll-for="' + id + '"]');
        const c = w.querySelector('tbody tr > :first-child'); const x0 = c.getBoundingClientRect().left;
        const can = w.scrollWidth > w.clientWidth + 1; w.scrollLeft = 200; const x1 = c.getBoundingClientRect().left; w.scrollLeft = 0;
        return {scrolls: can, x0: x0, x1: x1}; }""", tid)
    if inline["scrolls"] and abs(inline["x0"] - inline["x1"]) > 1:
        return "inline first column moved %.0f px on a sideways scroll" % (inline["x1"] - inline["x0"])
    btn.scroll_into_view_if_needed()
    btn.click()
    page.wait_for_timeout(350)
    r = page.evaluate("""() => { const d = document.getElementById('table-dialog'); if (!d || !d.open) return null;
        const b = d.getBoundingClientRect(), w = d.querySelector('.table-wrap'), c = w.querySelector('tbody tr > :first-child');
        const x0 = c.getBoundingClientRect().left, can = w.scrollWidth > w.clientWidth + 1; w.scrollLeft = 200;
        const x1 = c.getBoundingClientRect().left; w.scrollLeft = 0;
        return {w: b.width, h: b.height, vw: innerWidth, vh: innerHeight, scrolls: can, x0: x0, x1: x1,
                title: document.getElementById('table-dialog-title').textContent,
                lock: getComputedStyle(document.documentElement).overflow}; }""")
    if r is None:
        return "the dialog did not open"
    page.screenshot(path=str(out_dir / ("dialog-%s-%d.png" % (tid, width))))
    title = page.evaluate("(id) => document.getElementById(id + '-title').textContent", tid)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    after = page.evaluate("""(id) => ({open: document.getElementById('table-dialog').open,
        focus: document.activeElement && document.activeElement.getAttribute('data-expand'),
        home: !!document.querySelector('[data-table-block="' + id + '"] .table-wrap table'),
        lock: getComputedStyle(document.documentElement).overflow})""", tid)
    if abs(r["w"] - r["vw"]) > 1 or abs(r["h"] - r["vh"]) > 1:
        return "dialog %dx%d in a %dx%d viewport" % (r["w"], r["h"], r["vw"], r["vh"])
    if r["title"] != title:
        return "dialog titled %r, table titled %r" % (r["title"][:40], title[:40])
    if r["lock"] != "hidden":
        return "background scroll not locked"
    if r["scrolls"] and abs(r["x0"] - r["x1"]) > 1:
        return "first column moved %.0f px in the dialog" % (r["x1"] - r["x0"])
    if after["open"]:
        return "Esc did not close the dialog"
    if after["focus"] != tid:
        return "focus went to %r, not the control" % after["focus"]
    if not after["home"] or after["lock"] == "hidden":
        return "the table did not go back, or the page stayed locked"
    return ""


def k6_ladder(browser, url, charts):
    page = browser.new_page(viewport={"width": DESIGN_WIDTH, "height": 900})
    page.goto(url, wait_until="networkidle")
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
    for cid in charts:
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
    page_name, charts = "", CHARTS
    if "--page" in argv:
        i = argv.index("--page")
        page_name = argv[i + 1]
        out_dir = OUT / pathlib.Path(page_name).stem
        argv = argv[:i] + argv[i + 2:]
    if "--charts" in argv:
        i = argv.index("--charts")
        charts = argv[i + 1].split(",")
        argv = argv[:i] + argv[i + 2:]
    tables, want_card, dialogs, describe = [], False, [], []
    if "--dialog" in argv:
        i = argv.index("--dialog")
        dialogs = argv[i + 1].split(",")
        argv = argv[:i] + argv[i + 2:]
    if "--describe" in argv:
        i = argv.index("--describe")
        describe = argv[i + 1].split(",")
        argv = argv[:i] + argv[i + 2:]
    if "--tables" in argv:
        i = argv.index("--tables")
        tables = argv[i + 1].split(",")
        argv = argv[:i] + argv[i + 2:]
    if "--card" in argv:
        want_card = True
        argv.remove("--card")
    url = URL + page_name
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
    overflow_failures, draw_failures, dialog_failures = [], [], []
    record = {"url": url, "widths": [], "breakpoints": [], "crossings": [], "per_width": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        if widths:
            print("explicit widths: %s" % ", ".join(str(w) for w in widths))
            bps, crossings = [], []
        else:
            widths, bps, crossings = k6_ladder(browser, url, charts)
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
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(1500)
            if errors:
                print("  CONSOLE ERRORS at %dpx:" % width)
                for e in errors[:8]:
                    print("    " + e)
            page.screenshot(path=str(out_dir / ("page-%d.png" % width)), full_page=True)
            for cid in charts:
                card = page.locator("#card-" + cid)
                target = card if card.count() else page.locator("#" + cid)
                # A card taller than the viewport is scrolled to its centre for the capture, which slid it
                # under the sticky site header (c4 at 320 px). The header is made static for the shot only;
                # the page a reader loads is unchanged.
                target.screenshot(path=str(out_dir / ("%s-%d.png" % (cid, width))),
                                  style="#site-header{position:static !important}")
            # The named tables and the card, at the narrowest and the design width only. A table's details is
            # opened for the shot, which is the state the reader asks for; the cue is then re-measured by page.js.
            if width in (NARROW_WIDTH, DESIGN_WIDTH):
                for tid in tables:
                    block = page.locator('[data-table-block="%s"]' % tid)
                    if not block.count():
                        draw_failures.append((width, "table " + tid))
                        continue
                    page.evaluate("(id) => { const d = document.querySelector('[data-table-block=\"' + id + '\"]').closest('details'); "
                                  "if (d) d.open = true; }", tid)
                    page.wait_for_timeout(250)
                    block.screenshot(path=str(out_dir / ("table-%s-%d.png" % (tid, width))),
                                     style="#site-header{position:static !important}")
                if want_card:
                    c = page.locator('[data-case="card"]')
                    if not c.count():
                        draw_failures.append((width, "card"))
                    else:
                        c.screenshot(path=str(out_dir / ("card-%d.png" % width)))
                # A chart's description opened for the shot (Build Brief 2.3); closed, it is the chart render itself.
                for cid in describe:
                    page.evaluate("(id) => { const d = document.querySelector('#card-' + id + ' details.chart-description'); if (d) d.open = true; }", cid)
                    page.wait_for_timeout(200)
                    page.locator("#card-" + cid).screenshot(path=str(out_dir / ("%s-described-%d.png" % (cid, width))),
                                                           style="#site-header{position:static !important}")
                    page.evaluate("(id) => { document.querySelector('#card-' + id + ' details.chart-description').open = false; }", cid)
                # The full-screen table, driven as a reader drives it (Build Brief 2.3 step 4): the control clicked, the
                # dialog measured against the viewport, the table scrolled sideways with the first column checked in
                # place, Esc pressed, focus checked on the control. A behaviour check, not a reading of the markup.
                for tid in dialogs:
                    fail = dialog_check(page, tid, width, out_dir)
                    if fail:
                        dialog_failures.append((width, tid, fail))
                    print("  width %d: dialog %s %s" % (width, tid, "FAILED: " + fail if fail else "fills the viewport, first column pinned, Esc closes, focus returns"))
            seg = page.evaluate(
                """() => Array.from(document.querySelectorAll('.cascadia-provenance'))
                        .map(n => n.textContent.split(' \\u00b7 ').length)""")
            dims = page.evaluate(
                """(ids) => Object.fromEntries(ids.map(id => {
                     const cv = document.getElementById(id).querySelector('canvas');
                     return [id, cv ? cv.width + 'x' + cv.height : 'none'];
                   }))""", charts)
            grid = page.evaluate(
                """(ids) => Object.fromEntries(ids.map(id => {
                     try {
                       const ch = echarts.getInstanceByDom(document.getElementById(id));
                       const g = ch.getModel().getComponent('grid').coordinateSystem.getRect();
                       return [id, Math.round(g.width)];
                     } catch (e) { return [id, 'n/a']; }
                   }))""", charts)
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
    if dialog_failures:
        print("\nTABLE DIALOG FAILED: %s" % dialog_failures)
        sys.exit(1)
    if overflow_failures:
        print("\nRULE 5.3 / WCAG 1.4.10 FAILED, the page scrolls sideways:")
        for w, sw, cw in overflow_failures:
            print("  at %d px the document is %d px wide (over by %d)" % (w, sw, sw - cw))
        sys.exit(1)


if __name__ == "__main__":
    main()
