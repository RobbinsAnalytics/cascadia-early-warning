"""Tap tooltips on a touch device, hover tooltips on a desktop (D22, Build Brief 2.4 step 3).

A behaviour check in Chromium, not a reading of page.js. On an emulated phone (390 x 844, hasTouch, isMobile)
each chart on each page is scrolled so its plot fills the screen with its title above the fold, the way a reader
holds a phone, and one of its marks is tapped. The readout must then be visible, wholly inside the viewport and
below the sticky site header, and not under the tap point. In a desktop context (fine pointer, 1040 wide) a hover over the same mark must show the
hover tooltip. One screenshot per page of a tapped readout goes to docs/renders/tap-<page>.png.

The page is served at http://localhost:8731/ (python -m http.server 8731 --directory docs). Exit non-zero on any
failure.

    python src/test_tap_tooltips.py
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "renders"
URL = "http://localhost:8731/"
PAGES = {"index.html": ["c1", "c2", "c3", "c4", "c5"], "case-study.html": ["c3"]}
SHOT = {"index.html": "c2", "case-study.html": "c3"}

# The mark to tap, in viewport pixels, for each chart: a data point in the middle of the series the readout
# describes, located through ECharts' own convertToPixel. The page is scrolled first so the plot's top sits just
# below the sticky site header and the chart's title is above the fold.
MARK = r"""
(id) => {
  const host = document.getElementById(id), ch = echarts.getInstanceByDom(host);
  const grid = ch.getModel().getComponent('grid', 0).coordinateSystem.getRect();
  const o = ch.getOption(), r0 = host.getBoundingClientRect();
  const hdr = document.getElementById('site-header'), hb = hdr ? hdr.getBoundingClientRect().height : 0;
  window.scrollTo(0, window.scrollY + r0.top + grid.y - hb - 8);   // the plot's top just below the sticky header
  const r = host.getBoundingClientRect();
  let px = null;
  if (id === 'c3') {
    const i = Math.floor(o.series[0].data.length / 2), v = o.series[0].data[i].value;
    px = ch.convertToPixel({ seriesIndex: 0 }, [v / 2, i]);
  } else if (id === 'c4') {
    const s = o.series[1], f = s.data[Math.floor(s.data.length / 2)].value;
    px = ch.convertToPixel({ seriesIndex: 1 }, [f[0], f[1]]);
  } else {
    // the line the readout describes: received (c1 series 3, c2 series 4), within 3 months (c5 series 2)
    const si = { c1: 3, c2: 4, c5: 2 }[id], data = o.series[si].data, i = Math.floor(data.length * 0.6);
    px = ch.convertToPixel({ seriesIndex: si }, [i, data[i]]);
  }
  return { x: Math.round(r.left + px[0]), y: Math.round(r.top + px[1]), titleTop: Math.round(r.top) };
}
"""

BOX = r"""
(id) => {
  const host = document.getElementById(id);
  const tips = Array.from(host.querySelectorAll('div')).filter(d => /z-index:\s*9999999/.test(d.getAttribute('style') || ''));
  const t = tips.find(d => getComputedStyle(d).display !== 'none' && parseFloat(getComputedStyle(d).opacity) > 0.5
                           && d.textContent.trim().length > 0);
  if (!t) return null;
  const b = t.getBoundingClientRect();
  return { left: b.left, top: b.top, right: b.right, bottom: b.bottom, text: t.textContent.trim().slice(0, 60) };
}
"""


def main() -> int:
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True,
                                    is_mobile=True)
        for page_name, charts in PAGES.items():
            pg = phone.new_page()
            pg.goto(URL + page_name, wait_until="networkidle")
            pg.wait_for_timeout(1200)
            capability = pg.evaluate("() => matchMedia('(hover: hover) and (pointer: fine)').matches")
            if capability:
                failures.append("%s: the phone context reports a fine pointer; the test proves nothing" % page_name)
            for cid in charts:
                m = pg.evaluate(MARK, cid)
                pg.wait_for_timeout(300)
                m = pg.evaluate(MARK, cid)   # after the scroll settles
                pg.wait_for_timeout(200)
                pg.touchscreen.tap(m["x"], m["y"])
                pg.wait_for_timeout(500)
                b = pg.evaluate(BOX, cid)
                vw, vh = 390, 844
                # the visible top is below the sticky site header
                hdr = pg.evaluate("() => { const h = document.getElementById('site-header'); return h ? Math.max(0, h.getBoundingClientRect().bottom) : 0; }")
                if b is None:
                    msg = "no readout after a tap"
                elif not (b["left"] >= 0 and b["top"] >= hdr and b["right"] <= vw and b["bottom"] <= vh):
                    msg = "readout outside the viewport %s" % b
                elif b["left"] <= m["x"] <= b["right"] and b["top"] <= m["y"] <= b["bottom"]:
                    msg = "readout under the tap point"
                elif m["titleTop"] >= 0:
                    msg = "the chart's title was not above the fold (the test did not hold the phone as a reader does)"
                else:
                    msg = ""
                print("  phone 390x844 %-15s %s: %s" % (page_name, cid, msg or "readout visible, inside the viewport, "
                      "clear of the tap at (%d, %d): %r" % (m["x"], m["y"], b["text"])))
                if msg:
                    failures.append("%s %s: %s" % (page_name, cid, msg))
                if cid == SHOT[page_name] and not msg:
                    pg.screenshot(path=str(OUT / ("tap-%s.png" % pathlib.Path(page_name).stem)))
                pg.touchscreen.tap(5, 5)
                pg.wait_for_timeout(200)
            pg.close()
        phone.close()

        desk = browser.new_context(viewport={"width": 1040, "height": 900})
        for page_name, charts in PAGES.items():
            pg = desk.new_page()
            pg.goto(URL + page_name, wait_until="networkidle")
            pg.wait_for_timeout(1200)
            for cid in charts:
                m = pg.evaluate(MARK, cid)
                pg.wait_for_timeout(300)
                m = pg.evaluate(MARK, cid)
                pg.mouse.move(m["x"] - 3, m["y"] - 3)
                pg.mouse.move(m["x"], m["y"])
                pg.wait_for_timeout(400)
                b = pg.evaluate(BOX, cid)
                msg = "" if b else "no hover tooltip"
                print("  desktop 1040  %-15s %s: %s" % (page_name, cid, msg or "hover tooltip shown: %r" % b["text"]))
                if msg:
                    failures.append("desktop %s %s: %s" % (page_name, cid, msg))
                pg.mouse.move(2, 2)
            pg.close()
        browser.close()
    if failures:
        print("\nTAP TOOLTIP TEST FAILED:")
        for f in failures:
            print("  " + f)
        return 1
    print("\nTap tooltip test passed: %d phone taps, %d desktop hovers." % (sum(map(len, PAGES.values())), sum(map(len, PAGES.values()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
