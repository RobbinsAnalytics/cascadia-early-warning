/**
 * Cascadia Early Warning: chart layer.
 *
 * Reads the build-time data block written by src/build_page.py. No figure or
 * sentence is composed here that is not already in that block (K2): every
 * title, subtitle, annotation, summary and aria-label arrives as a string,
 * and this file decides geometry only.
 *
 * FIVE CHARTS. Four are time forms and call cascadiaNavigator (Rule 5.1
 * layer 3): c1 (series and outlook), c2 (the locked test), c4 (the review
 * timeline) and c5 (the lag-matched series). c3 is a ranked bar whose table
 * carries the finding as well as the canvas does, and carries an L3 shape
 * clause in its summary instead.
 *
 * COLOURS ARE FIXED ACROSS THE PAGE (Rule 2.3.1): actual reports = Evergreen;
 * the model in use's points and ranges = Glacier; the other model = Rain,
 * directly labelled (2.3.6 exception); flagged months and Class I markers =
 * Madrona, with the sign carried by the label (2.3.2). Nothing of Felix is
 * drawn inside a canvas (D15).
 *
 * RULE 4.5. The next-month figure in c1 is a quantile dotplot of twenty
 * outcomes from the model's own error history, drawn beside the series; the
 * 80% range in c1, c2 is a band, never a bare error bar.
 */
(function () {
  'use strict';

  /**
   * TABLE SCROLL CUES (Build Brief 2.2 step 7). Each table's cue, written into the page by build_page.py,
   * is shown only while its wrapper scrolls sideways: on load, on resize, and when a details element
   * opens (a closed one has no width). Geometry only; the words are the page's. Run before any chart,
   * so a chart that fails to draw cannot leave the cues unset.
   */
  function scrollCues() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-scroll-cue]'), function (cue) {
      var wrap = document.querySelector('[data-scroll-for="' + cue.getAttribute('data-scroll-cue') + '"]');
      cue.hidden = !(wrap && wrap.scrollWidth > wrap.clientWidth + 1);
    });
  }
  scrollCues();
  document.addEventListener('toggle', scrollCues, true);
  window.addEventListener('load', scrollCues);
  (function () {
    var t = null;
    window.addEventListener('resize', function () { if (t) clearTimeout(t); t = setTimeout(scrollCues, 120); });
  })();

  var D = JSON.parse(document.getElementById('cascadia-data').textContent);
  var C = CASCADIA.colors, INK = CASCADIA.textInk;
  var SANS = CASCADIA.sans, SERIF = CASCADIA.serif;

  function el(id) { return document.getElementById(id); }
  function nf(n) { return Math.round(Number(n)).toLocaleString('en-US'); }
  function pct(x) { return Math.round(100 * x) + '%'; }

  var _m = document.createElement('canvas').getContext('2d');
  function textWidth(text, font) { _m.font = font; return _m.measureText(String(text)).width; }
  function prewrap(text, px, font) {
    _m.font = font;
    var words = String(text).split(' '), lines = [], cur = '';
    for (var i = 0; i < words.length; i++) {
      var test = cur ? cur + ' ' + words[i] : words[i];
      if (_m.measureText(test).width > px && cur) { lines.push(cur); cur = words[i]; }
      else { cur = test; }
    }
    lines.push(cur);
    return lines.join('\n');
  }
  var TITLE_FONT = '600 17px ' + SERIF, SUB_FONT = '12px ' + SANS, ANN_FONT = '13px ' + SERIF;

  function titleBlock(L, finding, subtitle) {
    var px = L.w - 24;
    var f = prewrap(finding, px, TITLE_FONT), s = prewrap(subtitle, px, SUB_FONT);
    var tl = f.split('\n').length, sl = s.split('\n').length;
    var title = cascadiaTitle(f, s, { width: L.w - 14 });
    // The vendored helper sets no subtitle line height, so ECharts drew the lines tighter than the 18 px
    // per line budgeted here and left a dead band above every plot (long subtitles at 320 px lost
    // 100 px and more). The line height is set to the budget; the theme file is not edited.
    title.subtextStyle.lineHeight = 18;
    // 30 px below the subtitle: the value axis's name stands about 22 px above the plot it names.
    return { title: title, top: Math.round(6 + tl * 26 + 6 + sl * 18 + 30) };
  }
  function annotation(text, opts) {
    var w = opts.width || 180;
    var mp = cascadiaAnnotation(prewrap(text, w - 6, ANN_FONT), opts);
    if (opts.fontSize) mp.data[0].label.fontSize = opts.fontSize;
    return mp;
  }
  function niceAxis(maxVal, headroom, ticks) {
    var target = Math.max(1, (maxVal * headroom) / (ticks || 4));
    var mag = Math.pow(10, Math.floor(Math.log(target) / Math.LN10));
    var step = null, cands = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < cands.length; i++) {
      if (cands[i] * mag >= target) { step = cands[i] * mag; break; }
    }
    return { max: Math.ceil(Math.max(1, maxVal * headroom) / step) * step, interval: step };
  }
  function monthShort(ym) {
    var names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return names[parseInt(ym.slice(5, 7), 10) - 1] + ' ' + ym.slice(0, 4);
  }
  function monthTick(ym, narrow) {
    var names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    // Declared abbreviation at the narrow width (Rule 5.5): "Jan 2024" -> "Jan '24".
    return narrow ? names[parseInt(ym.slice(5, 7), 10) - 1] + " '" + ym.slice(2, 4)
                  : names[parseInt(ym.slice(5, 7), 10) - 1] + ' ' + ym.slice(0, 4);
  }

  /**
   * EVERY WIDTH AT WHICH THIS PAGE CHANGES ITS MIND, DECLARED IN ONE PLACE.
   * One breakpoint, measured on the HOST element's width, not the window.
   * Below it in-plot annotations become the note under the plot, tick labels
   * take their declared abbreviation, c3's value labels drop their unit, and
   * c4's lane labels shorten to the code alone.
   */
  var BP = { narrow: 560 };
  window.CASCADIA_BREAKPOINTS = [BP.narrow];

  function layout(host) {
    var w = host.clientWidth || CASCADIA.minCanvasPx;
    return { w: w, narrow: w < BP.narrow,
             // No tooltip at or below a 768 px viewport (CHART-REVIEW 5.5 fails a hover-following
             // tooltip there, and the drop order makes it the first thing to go); the table and the
             // keyboard navigator carry the values. The decision Matter Ledger recorded, kept here.
             noTip: window.innerWidth <= 768,
             tapTip: !(window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches) };
  }
  function tip(L, opts) {
    return {
      show: !L.noTip, trigger: opts.trigger || 'item', confine: true, appendToBody: false,
      triggerOn: L.tapTip ? 'mousemove|click' : 'mousemove',
      position: L.tapTip ? function (pt, params, dom, rect, size) {
        var cw = size.contentSize[0], chh = size.contentSize[1];
        var x = Math.max(4, Math.min(Math.round(pt[0] - cw / 2), size.viewSize[0] - cw - 4));
        var y = Math.round(pt[1] - chh - 18);
        if (y < 4) y = Math.round(pt[1] + 26);
        return [x, y];
      } : undefined,
      formatter: opts.formatter
    };
  }
  function finish(host, ch, spec, L) {
    // ECharts writes its own generated aria-label onto the host on every render, including the resize that
    // cascadiaResize schedules, and so overwrote the label set below with one built from series names. Giving
    // it the authored text as its description makes the label it writes the authored one.
    ch.setOption({ aria: { enabled: true, label: { description: spec.ariaLabel } } });
    cascadiaResize(host, ch);
    cascadiaProvenance(host, spec.provenance);
    el('sum-' + host.id).textContent = spec.summary;
    cascadiaAccessible(host, { label: spec.ariaLabel, summaryId: 'sum-' + host.id, tableId: 'tbl-' + host.id });
    if (spec.nav) cascadiaNavigator(host, spec.nav);
    var note = el('note-' + host.id);
    if (note) note.hidden = !(spec.noteVisible == null ? L.narrow : spec.noteVisible);
    return ch;
  }
  function mount(id, build) {
    var host = el(id), state = { mode: null, chart: null };
    if (!host) return;   // a page may carry a subset of the charts (docs/case-study.html carries chart 3 only)
    function run() {
      var L = layout(host), mode = (L.narrow ? 'n' : 'w') + (L.noTip ? 't' : '');
      if (state.chart && state.mode === mode) return;
      if (state.chart) state.chart.dispose();
      state.mode = mode;
      state.chart = build(host, L);
    }
    run();
    var t = null;
    window.addEventListener('resize', function () { if (t) clearTimeout(t); t = setTimeout(run, 120); });
  }
  function axisLabelX(L, n, plotW) {
    var lab = { hideOverlap: true, interval: 'auto', showMinLabel: true, showMaxLabel: true, fontFamily: SANS, fontSize: 12 };
    if (L.narrow) {
      // At the narrow width the renderer's own thinning left the first two labels touching once the
      // first was pulled inside the plot, so the density is a declared rule keyed to the plot width
      // (K4): at least three labels, first, last and evenly spaced between, never closer than 64 px.
      var maxLabels = Math.max(3, Math.floor(plotW / 64)), step = Math.max(1, Math.ceil((n - 1) / (maxLabels - 1)));
      lab.interval = function (index) { return index === 0 || index === n - 1 || (index % step === 0 && index <= n - 1 - step / 2); };
      lab.alignMinLabel = 'left'; lab.alignMaxLabel = 'right';
    }
    return lab;
  }
  function plural(k, word) { return k + ' ' + word + (k === 1 ? '' : 's'); }
  function alpha(hex, a) {
    var h = hex.replace('#', '');
    return 'rgba(' + parseInt(h.slice(0, 2), 16) + ',' + parseInt(h.slice(2, 4), 16) + ',' + parseInt(h.slice(4, 6), 16) + ',' + a + ')';
  }
  function lastIndex(arr) { for (var i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return i; return -1; }

  /**
   * Rule 5.5: an end label is never dropped at the narrow width; it takes a
   * declared abbreviation instead, and the gutter that holds it is measured
   * from the text rather than guessed. Every narrow form is listed here, once.
   * "(in use)" is a qualifier the subtitle restates, so the narrow form drops it.
   */
  var ABBR = { 'expected': 'exp.', 'received': 'rec.', 'trailing mean': 'mean', 'candidate': 'cand.',
               'candidate (in use)': 'cand.', 'trailing mean (in use)': 'mean',
               'within 12 months': '12 mo', 'within 6': '6 mo', 'within 3': '3 mo' };
  function endText(text, L) { return L.narrow ? (ABBR[text] || text) : text; }
  function endLabel(text, L, color) {
    return { show: true, formatter: endText(text, L), color: color, fontFamily: SANS, fontSize: 12, distance: 8 };
  }
  function gutter(texts, L) {
    return Math.ceil(Math.max.apply(null, texts.map(function (t) { return textWidth(endText(t, L), '12px ' + SANS); }))) + 14;
  }

  /**
   * Direct labels at the right end of line series collide where the lines
   * converge (every chart here ends with its series within a few pixels of
   * one another). After the first draw, measure each label's anchor in pixels
   * and push the labels apart to a minimum gap, keeping the group centred on
   * where it was; the lines themselves do not move. `items` is
   * [{ seriesIndex, dataIndex, value }], one per labelled series; `extra`
   * merges further endLabel fields (c1 needs a longer distance to clear the
   * dotplot column that stands between the line ends and the labels).
   */
  function spreadEndLabels(ch, items, minGap, extra) {
    var pts = items.map(function (it) {
      var p = ch.convertToPixel({ seriesIndex: it.seriesIndex }, [it.dataIndex, it.value]);
      return { it: it, y: p ? p[1] : 0 };
    }).sort(function (a, b) { return a.y - b.y; });
    var placed = [];
    pts.forEach(function (p, i) { placed.push(i === 0 ? p.y : Math.max(p.y, placed[i - 1] + minGap)); });
    var lift = (placed[placed.length - 1] - pts[pts.length - 1].y) / 2;
    var series = [];
    pts.forEach(function (p, i) {
      var patch = { endLabel: { offset: [0, Math.round(placed[i] - lift - p.y)] } };
      if (extra) Object.keys(extra).forEach(function (k) { patch.endLabel[k] = extra[k]; });
      series[p.it.seriesIndex] = patch;
    });
    for (var k = 0; k < series.length; k++) if (!series[k]) series[k] = {};
    ch.setOption({ series: series });
  }

  /* ================= c1 · the series, the points, and the outlook as a dotplot ================= */
  /**
   * Below the breakpoint chart 1 stacks: the history on top, and the outlook's twenty outcomes as a
   * horizontal strip underneath on the history's own value scale, so the plot keeps the full width
   * instead of sharing it with a dot column (at 320 px the history had a 110 px plot). The band's
   * "80% range" label sits in a row reserved above the plot, with a leader to where the band begins,
   * so it never crosses the axis labels; the strip is headed by its month and horizon.
   */
  function c1Stacked(host, L) {
    var d = D.c1, n = d.months.length, O = d.outlook;
    var tb = titleBlock(L, d.finding, d.subtitle), top = tb.top;
    var endLabelW = gutter(['expected', 'received'], L);
    var BAND_ROW = 18;
    var plotW = Math.max(140, L.w - 48 - endLabelW);
    var plotH = cascadiaBankedHeight(d.actual, plotW, { min: 200, max: 300 }) || 240;
    var gTop = top + BAND_ROW;
    var annText = prewrap(d.annotation, L.w - 16, ANN_FONT), annLines = annText.split('\n').length;
    var headTop = gTop + plotH + 34, annTop = headTop + 20;
    var stripTop = annTop + annLines * 17 + 14, stripH = 66;
    host.style.height = (stripTop + stripH + 34) + 'px';
    var allVals = d.actual.concat(d.hi80.filter(function (v) { return v != null; }), [O.hi80], O.dots);
    var ax = niceAxis(Math.max.apply(null, allVals), 1.12, 7);
    var lo = d.lo80.slice(), span = d.hi80.map(function (v, i) { return v == null || d.lo80[i] == null ? null : v - d.lo80[i]; });
    var iBand = -1;
    for (var q = 0; q < n; q++) { if (d.hi80[q] != null) { iBand = q; break; } }
    var binStep = ax.interval / 4, bins = {};
    O.dots.forEach(function (v) { var b = Math.round(v / binStep); (bins[b] = bins[b] || []).push(v); });
    function dotStrip(params, api) {
      var cs = params.coordSys, base = cs.y + cs.height - 8, kids = [];
      function x(v) { return api.coord([v, 0])[0]; }
      kids.push({ type: 'line', shape: { x1: x(O.lo80), y1: base + 6, x2: x(O.hi80), y2: base + 6 }, style: { stroke: INK.glacier, lineWidth: 1 } });
      kids.push({ type: 'line', shape: { x1: x(O.point), y1: base + 6, x2: x(O.point), y2: base - 30 }, style: { stroke: INK.glacier, lineWidth: 2 } });
      Object.keys(bins).forEach(function (b) {
        var vs = bins[b], cx = x(parseInt(b, 10) * binStep);
        vs.forEach(function (v, k) {
          var inside = v >= O.lo80 && v <= O.hi80;
          kids.push({ type: 'circle', shape: { cx: cx, cy: base - k * 6.5, r: 2.75 },
                      style: inside ? { fill: C.glacier } : { fill: C.paper, stroke: C.glacier, lineWidth: 1.5 }, z2: 2 });
        });
      });
      return { type: 'group', children: kids };
    }
    var kfmt = function (v) { return v >= 1000 ? (v / 1000) + 'K' : String(v); };
    var ch = echarts.init(host, 'cascadia');
    ch.setOption({
      title: tb.title,
      grid: [{ left: 8, right: endLabelW + 8, top: gTop, height: plotH, containLabel: true },
             { left: 8, right: 16, top: stripTop, height: stripH, containLabel: true }],
      xAxis: [{ gridIndex: 0, type: 'category', data: d.months.map(function (m) { return monthTick(m, true); }), boundaryGap: true,
                axisLabel: axisLabelX(L, n, plotW), axisTick: { show: false } },
              { gridIndex: 1, type: 'value', min: 0, max: ax.max, interval: ax.interval * 2, splitLine: { show: false }, axisLine: { show: true },
                axisLabel: { formatter: kfmt, showMaxLabel: false } }],
      yAxis: [{ gridIndex: 0, type: 'value', min: 0, max: ax.max, interval: ax.interval, name: 'reports received', nameLocation: 'end',
                nameGap: 8 + BAND_ROW, nameTextStyle: { color: C.slateMoss, fontFamily: SANS, fontSize: 12, align: 'left' },
                axisLabel: { formatter: kfmt } },
              { gridIndex: 1, type: 'category', data: [monthTick(O.target, true)], axisTick: { show: false }, axisLine: { show: false },
                axisLabel: { fontFamily: SANS, fontSize: 12, color: C.slateMoss } }],
      tooltip: { show: false },
      series: [
        { name: '80% range low', type: 'line', stack: 'band', data: lo, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, z: 1 },
        { name: '80% range', type: 'line', stack: 'band', data: span, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0 },
          areaStyle: { color: C.glacier, opacity: 0.18 }, itemStyle: { opacity: 0 }, z: 1 },
        { name: d.modelLabel + ' point', type: 'line', data: d.points, showSymbol: false, symbol: 'none', connectNulls: false,
          lineStyle: { color: C.glacier, width: 2, type: 'dashed' }, itemStyle: { color: C.glacier }, z: 3, endLabel: endLabel('expected', L, INK.glacier) },
        { name: 'Reports received', type: 'line', data: d.actual, showSymbol: false, symbol: 'none',
          lineStyle: { color: C.evergreen, width: 2.5 }, itemStyle: { color: C.evergreen }, z: 4, endLabel: endLabel('received', L, INK.evergreen) },
        { name: O.navName, type: 'custom', xAxisIndex: 1, yAxisIndex: 1, renderItem: dotStrip,
          data: [[O.point, 0]], clip: false, silent: true, z: 5 }
      ]
    });
    var ip = lastIndex(d.points);
    spreadEndLabels(ch, [{ seriesIndex: 2, dataIndex: ip, value: d.points[ip] }, { seriesIndex: 3, dataIndex: n - 1, value: d.actual[n - 1] }], 15);
    var g = [
      { type: 'text', x: 8, y: headTop, style: { text: O.navName, fill: C.slateMoss, font: '600 12px ' + SANS } },
      { type: 'text', x: 8, y: annTop, style: { text: annText, fill: INK.glacier, font: ANN_FONT, lineHeight: 17 } }
    ];
    if (iBand >= 0) {
      var bx = ch.convertToPixel({ seriesIndex: 3 }, [iBand, d.hi80[iBand]]);
      // The label names the month the band begins: at this width the leader stands between tick labels and was
      // read as the band starting at the nearest one (panel 2026-10-07).
      g.push({ type: 'text', x: Math.round(bx[0]), y: gTop - 15, style: { text: '80% range from ' + monthTick(d.months[iBand], true), fill: INK.glacier, font: '12px ' + SANS } });
      g.push({ type: 'line', shape: { x1: Math.round(bx[0]) + 0.5, y1: gTop - 2, x2: Math.round(bx[0]) + 0.5, y2: Math.round(bx[1]) },
               style: { stroke: INK.glacier, lineWidth: 1, opacity: 0.6 } });
    }
    ch.setOption({ graphic: g });
    return finish(host, ch, {
      provenance: d.provenance, summary: d.summary, ariaLabel: d.ariaLabel, noteVisible: false,
      nav: c1Nav(ch, d, O)
    }, L);
  }
  function c1Nav(ch, d, O) {
    return { chart: ch, label: d.ariaLabel, series: [
      { name: 'Reports received', summary: 'from ' + nf(d.actual[0]) + ' to ' + nf(d.actual[d.months.length - 1]),
        points: d.months.map(function (m, i) { return { label: monthShort(m), value: nf(d.actual[i]), seriesIndex: 3, dataIndex: i }; }) },
      { name: d.modelLabel + ' one-month-ahead point', summary: 'where issued',
        points: d.months.map(function (m, i) { return d.points[i] == null ? null : { label: monthShort(m), value: nf(d.points[i]), seriesIndex: 2, dataIndex: i }; }).filter(Boolean) },
      { name: O.navName, summary: O.navSummary,
        points: [{ label: monthShort(O.target), value: nf(O.point), seriesIndex: 4, dataIndex: 0 }] }
    ] };
  }

  mount('c1', function (host, L) {
    if (L.narrow) return c1Stacked(host, L);
    var d = D.c1, n = d.months.length, O = d.outlook;
    var tb = titleBlock(L, d.finding, d.subtitle), top = tb.top;
    // Layout, left to right: the plot, the end labels, then the next month's dot column. The column is
    // drawn OUTSIDE the time axis by a custom series, so each label sits at its line's end and nothing
    // stands between a label and its line (panel finding 2).
    var endLabelW = gutter(['expected', 'received'], L), dotColW = L.narrow ? 44 : 96;
    var plotW = Math.max(140, L.w - 60 - dotColW - endLabelW);
    var ys = d.actual.slice();
    var allVals = ys.concat(d.hi80.filter(function (v) { return v != null; }), [O.hi80], O.dots);
    var plotH = cascadiaBankedHeight(ys, plotW, { min: 220, max: 340 }) || 280;
    host.style.height = (top + plotH + 60) + 'px';
    var ax = niceAxis(Math.max.apply(null, allVals), 1.12, 7);
    var lo = d.lo80.map(function (v) { return v == null ? null : v; });
    var span = d.hi80.map(function (v, i) { return v == null || d.lo80[i] == null ? null : v - d.lo80[i]; });
    var iBand = -1;
    for (var q = 0; q < n; q++) { if (d.hi80[q] != null) { iBand = q; break; } }
    var ch = echarts.init(host, 'cascadia');
    // The dotplot: twenty outcomes binned on the value axis and stepped sideways within a bin, so every
    // dot is visible and countable; dots inside the 80% range are filled and the rest hollow; a tick
    // marks the point and a thin rule spans the range (panel finding 1).
    var binStep = ax.interval / 4, bins = {};
    O.dots.forEach(function (v) { var b = Math.round(v / binStep); (bins[b] = bins[b] || []).push(v); });
    function columnX(xLast) { return xLast + endLabelW + dotColW / 2 + 4; }
    // The point's tick runs past the widest row of dots on both sides, so it shows beside the dots instead of
    // being covered by them (panel 2026-10-07: no seat could find it at the desktop width).
    var maxRow = 1;
    Object.keys(bins).forEach(function (b) { maxRow = Math.max(maxRow, bins[b].length); });
    var tickHalf = Math.round((maxRow - 1) / 2 * 7 + 3 + 8);
    function dotColumn(params, api) {
      var base = api.coord([n - 1, 0]), cx = columnX(base[0]), kids = [];
      function y(v) { return api.coord([n - 1, v])[1]; }
      kids.push({ type: 'line', shape: { x1: cx, y1: y(O.lo80), x2: cx, y2: y(O.hi80) }, style: { stroke: INK.glacier, lineWidth: 1 }, z2: 1 });
      kids.push({ type: 'line', shape: { x1: cx - tickHalf, y1: y(O.point), x2: cx + tickHalf, y2: y(O.point) }, style: { stroke: INK.glacier, lineWidth: 2 }, z2: 3 });
      Object.keys(bins).forEach(function (b) {
        var vs = bins[b], cy = y(parseInt(b, 10) * binStep);
        vs.forEach(function (v, k) {
          var inside = v >= O.lo80 && v <= O.hi80;
          kids.push({ type: 'circle', shape: { cx: cx + (k - (vs.length - 1) / 2) * 7, cy: cy, r: 3 },
                      style: inside ? { fill: C.glacier } : { fill: C.paper, stroke: C.glacier, lineWidth: 1.5 }, z2: 2 });
        });
      });
      kids.push({ type: 'text', style: { x: cx, y: base[1] + 8, text: monthTick(O.target, L.narrow), fill: C.slateMoss, font: '12px ' + SANS,
                                         align: 'center', textAlign: 'center', verticalAlign: 'top', textVerticalAlign: 'top' } });
      // The column's horizon, under its month: the history's band is one month ahead, the column is not.
      kids.push({ type: 'text', style: { x: cx, y: base[1] + 24, text: O.tickNote, fill: C.slateMoss, font: '12px ' + SANS,
                                         align: 'center', textAlign: 'center', verticalAlign: 'top', textVerticalAlign: 'top' } });
      return { type: 'group', children: kids };
    }
    var option = {
      title: tb.title,
      grid: { left: 8, right: endLabelW + dotColW + 12, top: top, height: plotH, containLabel: true },
      xAxis: { type: 'category', data: d.months.map(function (m) { return monthTick(m, L.narrow); }), boundaryGap: true,
               axisLabel: axisLabelX(L, n, plotW), axisTick: { show: false } },
      yAxis: { type: 'value', min: 0, max: ax.max, interval: ax.interval, name: 'reports received', nameLocation: 'end', nameGap: 8,
               nameTextStyle: { color: C.slateMoss, fontFamily: SANS, fontSize: 12, align: 'left' },
               axisLabel: { formatter: function (v) { return v >= 1000 ? (v / 1000) + 'K' : String(v); } } },
      tooltip: tip(L, { trigger: 'axis', formatter: function (qs) {
        var i = qs[0].dataIndex;
        var s = monthShort(d.months[i]) + '<br>received: ' + nf(d.actual[i]);
        if (d.points[i] != null) s += '<br>' + d.modelLabel + ' point: ' + nf(d.points[i]);
        if (d.lo80[i] != null) s += '<br>80% range ' + nf(d.lo80[i]) + ' to ' + nf(d.hi80[i]);
        return s;
      } }),
      series: [
        { name: '80% range low', type: 'line', stack: 'band', data: lo, showSymbol: false, symbol: 'none',
          lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, tooltip: { show: false }, z: 1 },
        { name: '80% range', type: 'line', stack: 'band', data: span, showSymbol: false, symbol: 'none',
          lineStyle: { opacity: 0 }, areaStyle: { color: C.glacier, opacity: 0.18 }, itemStyle: { opacity: 0 },
          tooltip: { show: false }, z: 1 },
        { name: d.modelLabel + ' point', type: 'line', data: d.points, showSymbol: false, symbol: 'none', connectNulls: false,
          lineStyle: { color: C.glacier, width: 2, type: 'dashed' }, itemStyle: { color: C.glacier }, z: 3,
          endLabel: endLabel('expected', L, INK.glacier),
          // The band is named where it begins (panel finding 5): a subordinate label.
          markPoint: iBand < 0 ? undefined : { symbol: 'circle', symbolSize: 0, data: [{ coord: [iBand, d.hi80[iBand]],
            label: { show: true, formatter: L.narrow ? '80% range' : '80% range from ' + monthShort(d.months[iBand]), position: 'top',
                     distance: 6, color: INK.glacier, fontFamily: SANS, fontSize: 12, align: 'right' } }] } },
        { name: 'Reports received', type: 'line', data: d.actual, showSymbol: false, symbol: 'none',
          lineStyle: { color: C.evergreen, width: 2.5 }, itemStyle: { color: C.evergreen }, z: 4,
          endLabel: endLabel('received', L, INK.evergreen) },
        { name: O.navName, type: 'custom', renderItem: dotColumn, data: [[n - 1, O.point]], clip: false,
          silent: true, z: 5, tooltip: { show: false } }
      ]
    };
    ch.setOption(option);
    var ip = lastIndex(d.points);
    spreadEndLabels(ch, [
      { seriesIndex: 2, dataIndex: ip, value: d.points[ip] },
      { seriesIndex: 3, dataIndex: n - 1, value: d.actual[n - 1] }
    ], 15);
    if (!L.narrow) {
      // The annotation is anchored in pixels above the column's highest dot.
      var topDot = Math.max.apply(null, O.dots);
      var px = ch.convertToPixel({ seriesIndex: 3 }, [n - 1, topDot]);
      var mp = annotation(d.annotation, { color: C.glacier, coord: [n - 1, topDot], position: 'top', distance: 14, align: 'right',
                                          width: Math.min(170, Math.round(plotW * 0.3)), container: L.w });
      delete mp.data[0].coord;
      mp.data[0].x = columnX(px[0]);
      mp.data[0].y = px[1];
      ch.setOption({ series: [{}, {}, {}, { markPoint: mp }] });
    }
    return finish(host, ch, {
      provenance: d.provenance, summary: d.summary, ariaLabel: d.ariaLabel,
      nav: c1Nav(ch, d, O)
    }, L);
  });

  /* ================= c2 · the locked test ================= */
  mount('c2', function (host, L) {
    var d = D.c2, n = d.months.length;
    var tb = titleBlock(L, d.finding, d.subtitle), top = tb.top;
    var useCand = d.model === 'candidate';
    var useName = useCand ? 'candidate' : 'trailing mean', otherName = useCand ? 'trailing mean' : 'candidate';
    // The right margin is measured from the longest direct label, not guessed.
    var endLabelW = gutter([useName + ' (in use)', otherName, 'received'], L);
    var plotW = Math.max(160, L.w - 70 - endLabelW);
    var plotH = cascadiaBankedHeight(d.actual, plotW, { min: 220, max: 340 }) || 280;
    host.style.height = (top + plotH + 60) + 'px';
    var allVals = d.actual.concat(d.candidate, d.baselineA, d.hi80);
    var ax = niceAxis(Math.max.apply(null, allVals), 1.18, 7);
    var span = d.hi80.map(function (v, i) { return v - d.lo80[i]; });
    var useSeries = useCand ? d.candidate : d.baselineA, otherSeries = useCand ? d.baselineA : d.candidate;
    var mi = d.miss.index;
    var ch = echarts.init(host, 'cascadia');
    var option = {
      title: tb.title,
      grid: { left: 8, right: endLabelW + 8, top: top, height: plotH, containLabel: true },
      xAxis: { type: 'category', data: d.months.map(function (m) { return monthTick(m, L.narrow); }), boundaryGap: false,
               axisLabel: axisLabelX(L, n, plotW), axisTick: { show: false } },
      yAxis: { type: 'value', min: 0, max: ax.max, interval: ax.interval, name: 'reports received', nameLocation: 'end', nameGap: 8,
               nameTextStyle: { color: C.slateMoss, fontFamily: SANS, fontSize: 12, align: 'left' },
               axisLabel: { formatter: function (v) { return v >= 1000 ? (v / 1000) + 'K' : String(v); } } },
      tooltip: tip(L, { trigger: 'axis', formatter: function (qs) {
        var i = qs[0].dataIndex;
        return monthShort(d.months[i]) + '<br>received: ' + nf(d.actual[i]) + '<br>candidate: ' + nf(d.candidate[i]) +
               '<br>trailing mean: ' + nf(d.baselineA[i]) + '<br>80% range (' + useName + '): ' + nf(d.lo80[i]) + ' to ' + nf(d.hi80[i]);
      } }),
      series: [
        { name: 'low', type: 'line', stack: 'band', data: d.lo80, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, tooltip: { show: false }, z: 1 },
        { name: '80% range', type: 'line', stack: 'band', data: span, showSymbol: false, symbol: 'none', lineStyle: { opacity: 0 },
          areaStyle: { color: C.glacier, opacity: 0.18 }, itemStyle: { opacity: 0 }, tooltip: { show: false }, z: 1 },
        { name: otherName, type: 'line', data: otherSeries, showSymbol: false, symbol: 'none',
          lineStyle: { color: C.rain, width: 2.5, type: 'dotted' }, itemStyle: { color: C.rain }, z: 2,
          endLabel: endLabel(otherName, L, C.slateMoss) },
        { name: useName, type: 'line', data: useSeries, showSymbol: false, symbol: 'none',
          lineStyle: { color: C.glacier, width: 2, type: 'dashed' }, itemStyle: { color: C.glacier }, z: 3,
          endLabel: endLabel(useName + ' (in use)', L, INK.glacier) },
        { name: 'Reports received', type: 'line', data: d.actual, showSymbol: false, symbol: 'none',
          lineStyle: { color: C.evergreen, width: 2.5 }, itemStyle: { color: C.evergreen }, z: 4,
          endLabel: endLabel('received', L, INK.evergreen),
          markLine: { symbol: 'none', silent: true, label: { show: false },
                      lineStyle: { color: INK.madrona, width: 1, type: 'solid' },
                      data: [[{ coord: [mi, d.miss.point] }, { coord: [mi, d.miss.actual] }]] } },
        // The months outside the band, ringed (panel: "which was the other one"); not navigated.
        { name: 'outside the 80% range', type: 'scatter', z: 5, silent: true, tooltip: { show: false },
          data: d.outside.map(function (o) { return [d.months.indexOf(o.month), o.actual]; }),
          symbol: 'circle', symbolSize: 14, itemStyle: { color: 'rgba(0,0,0,0)', borderColor: INK.madrona, borderWidth: 1.5 } }
      ]
    };
    if (!L.narrow) {
      option.series[4].markPoint = annotation(d.annotation, {
        color: C.madrona, coord: [mi, Math.max(d.miss.actual, d.miss.point)], position: 'top', distance: 10,
        align: mi > n / 2 ? 'right' : 'left', width: Math.min(260, Math.round(plotW * 0.5)), container: L.w
      });
    } else {
      // At the narrow width the annotation is the note under the plot; the mark keeps a two-word label so the leader is not bare.
      option.series[4].markPoint = { symbol: 'circle', symbolSize: 0, data: [{ coord: [mi, d.miss.actual],
        label: { show: true, formatter: 'largest miss', position: 'top', distance: 6, color: INK.madrona, fontFamily: SERIF, fontSize: 12 } }] };
    }
    ch.setOption(option);
    {
      spreadEndLabels(ch, [
        { seriesIndex: 2, dataIndex: n - 1, value: otherSeries[n - 1] },
        { seriesIndex: 3, dataIndex: n - 1, value: useSeries[n - 1] },
        { seriesIndex: 4, dataIndex: n - 1, value: d.actual[n - 1] }
      ], 15);
    }
    return finish(host, ch, {
      provenance: d.provenance, summary: d.summary, ariaLabel: d.ariaLabel,
      nav: { chart: ch, label: d.ariaLabel, series: [
        { name: 'Reports received', summary: 'range ' + nf(Math.min.apply(null, d.actual)) + ' to ' + nf(Math.max.apply(null, d.actual)),
          points: d.months.map(function (m, i) { return { label: monthShort(m), value: nf(d.actual[i]), seriesIndex: 4, dataIndex: i }; }) },
        { name: useName + ' point (in use)', summary: 'mean absolute error ' + nf(d.scores.use.mae),
          points: d.months.map(function (m, i) { return { label: monthShort(m), value: nf(useSeries[i]), seriesIndex: 3, dataIndex: i }; }) },
        { name: otherName + ' point', summary: 'mean absolute error ' + nf(useCand ? d.scores.baselineA.mae : d.scores.candidate.mae),
          points: d.months.map(function (m, i) { return { label: monthShort(m), value: nf(otherSeries[i]), seriesIndex: 2, dataIndex: i }; }) }
      ] }
    }, L);
  });

  /* ================= c3 · coverage of the 80% range, by code ================= */
  mount('c3', function (host, L) {
    var d = D.c3, rows = d.rows;
    var tb = titleBlock(L, d.finding, d.subtitle), top = tb.top;
    var labelW = L.narrow ? 64 : 150;
    var valueLabel = function (r) {
      var s = L.narrow ? pct(r.coverage80) : pct(r.coverage80) + ': ' + r.inside + ' of ' + r.n + ' months';
      if (!r.enabled) return s + (L.narrow ? ' rule off' : ', rule off');
      return s + (!L.narrow && 100 * r.coverage80 > d.band[1] ? ', above the gate band' : '');
    };
    var band = L.narrow ? 34 : 40;
    var refTop = L.narrow ? 0 : 24;
    var rightW = Math.ceil(Math.max.apply(null, rows.map(function (r) { return textWidth(valueLabel(r), '12px ' + SANS); }))) + 16;
    host.style.height = (top + refTop + rows.length * band + 56) + 'px';
    var ch = echarts.init(host, 'cascadia');
    var option = {
      title: tb.title,
      grid: { left: 8, right: rightW, bottom: 34, top: top + refTop, containLabel: true },
      // 100 is a true ceiling on a share (K1): the bound is not fitted.
      xAxis: { type: 'value', min: 0, max: 100, interval: L.narrow ? 50 : 20, name: 'months inside the 80% range', nameLocation: 'middle', nameGap: 28,
               axisLabel: { formatter: function (v) { return v + '%'; } } },
      yAxis: { type: 'category', inverse: true, data: rows.map(function (r) { return L.narrow ? r.code + ' ' + (r.model === 'candidate' ? 'cand.' : 'mean') : r.code + '  ' + (r.model === 'candidate' ? 'candidate' : 'trailing mean'); }),
               axisLabel: { width: labelW, overflow: 'truncate', fontFamily: SANS, fontSize: 12, interval: 0, margin: 10 } },
      tooltip: tip(L, { trigger: 'item', formatter: function (q) {
        var r = rows[q.dataIndex];
        return r.code + ' ' + r.name + '<br>' + r.modelLabel + '<br>80% coverage ' + pct(r.coverage80) + ' of ' + r.n + ' months<br>review rule ' + (r.enabled ? 'enabled' : 'disabled');
      } }),
      series: [{
        type: 'bar', barCategoryGap: '38%', z: 3,
        // The gate's expected band, 60% to 95%, as a shaded region under the bars (panel finding 10).
        markArea: { silent: true, itemStyle: { color: C.mist, opacity: 0.55 }, data: [[{ xAxis: d.band[0] }, { xAxis: d.band[1] }]] },
        data: rows.map(function (r) {
          // Disabled codes take Madrona with the word in the label (2.3.2); enabled take Evergreen.
          return { value: Math.round(1000 * r.coverage80) / 10,
                   itemStyle: { color: r.enabled ? C.evergreen : C.madrona },
                   label: { color: r.enabled ? INK.evergreen : INK.madrona } };
        }),
        label: { show: true, position: 'right', fontFamily: SANS, fontSize: 12, backgroundColor: C.paper, padding: [1, 3],
                 formatter: function (q) { return valueLabel(rows[q.dataIndex]); } },
        markLine: {
          symbol: 'none', silent: true,
          lineStyle: { color: 'rgba(0,0,0,0)', width: 1 },
          label: { show: !L.narrow, position: 'start', distance: 6, fontFamily: SANS, fontSize: 12, color: C.slateMoss,
                   formatter: function (p) { return p.name; } },
          data: [{ xAxis: d.nominal, name: 'nominal ' + d.nominal + '%', label: { align: 'left' } },
                 { xAxis: d.floor, name: d.floorLabel, label: { align: 'right', color: INK.madrona } }]
        }
      }, {
        // The two reference lines, drawn beneath the bars and their labels so a value label masks the line behind it (panel finding 8).
        type: 'custom', silent: true, z: 1, tooltip: { show: false }, data: [[d.floor, 0], [d.nominal, 0]],
        renderItem: function (params, api) {
          var x = api.coord([api.value(0), 0])[0], cs = params.coordSys;
          return { type: 'line', shape: { x1: x, y1: cs.y, x2: x, y2: cs.y + cs.height },
                   style: { stroke: api.value(0) === d.floor ? INK.madrona : C.slateMoss, lineWidth: 1, lineDash: [4, 4] } };
        }
      }]
    };
    ch.setOption(option);
    return finish(host, ch, { provenance: d.provenance, summary: d.summary, ariaLabel: d.ariaLabel, noteVisible: L.narrow }, L);
  });

  /* ================= c4 · what deserves review: flags, episodes, Class I initiations ================= */
  mount('c4', function (host, L) {
    var d = D.c4, months = d.months, lanes = d.lanes, n = months.length;
    var tb = titleBlock(L, d.finding, d.subtitle), top = tb.top;
    var laneH = L.narrow ? 34 : 40, labelW = L.narrow ? 58 : 150;
    // Headroom reserved above the first lane for the episode's label (K3); at the narrow width a short label
    // stands at the episode itself, because the full note under the plot was read as detached from it.
    var headTop = L.narrow ? 24 : 52;
    host.style.height = (top + headTop + lanes.length * laneH + 60) + 'px';
    var idx = {}; months.forEach(function (m, i) { idx[m] = i; });
    var flagData = [], epData = [], recData = [];
    // Diamonds are raised clear of the squares and same-month diamonds stepped a full glyph apart (panel
    // 2026-10-07: at the old offsets they touched the squares beneath them and each other).
    var dx = L.narrow ? 9 : 12, dy = L.narrow ? -11 : -14;
    lanes.forEach(function (l, li) {
      // A flagged month in a lane with the rule off is drawn hollow: real, and counting for nothing (panel finding 11).
      l.flagged.forEach(function (m) { flagData.push({ value: [idx[m], li], month: m, code: l.code,
        itemStyle: l.enabled ? { color: C.madrona } : { color: C.paper, borderColor: INK.madrona, borderWidth: 1.5 } }); });
      l.episodes.forEach(function (e) { epData.push({ value: [idx[e.start], li, idx[e.end], e.months, e.excess], code: l.code, e: e }); });
      // In a lane with the rule off, each episode the rule would open if it were on is drawn outlined: it opens
      // nothing, and it is what the title's second count counts.
      if (!l.enabled) l.ungated.forEach(function (e) { epData.push({ value: [idx[e.start], li, idx[e.end], e.months, 0], code: l.code, e: e, u: true }); });
      // Diamonds sit above the lane's centre line; same-month events step sideways so each is visible (panel finding 12).
      var seen = {};
      l.classI.forEach(function (r) { var k = seen[r.month] || 0; seen[r.month] = k + 1;
        recData.push({ value: [idx[r.month], li], code: l.code, r: r, symbolOffset: [k * dx, dy] }); });
    });
    var ch = echarts.init(host, 'cascadia');
    var option = {
      title: tb.title,
      grid: { left: 8, right: L.narrow ? 16 : 44, bottom: 34, top: top + headTop, containLabel: true },
      xAxis: { type: 'category', data: months.map(function (m) { return monthTick(m, L.narrow); }), boundaryGap: true,
               axisLabel: axisLabelX(L, n, L.w - 70 - labelW), axisTick: { show: false } },
      yAxis: { type: 'category', inverse: true,
               data: lanes.map(function (l) { return L.narrow ? l.code + (l.enabled ? '' : ' off') : l.code + (l.enabled ? '' : '  rule off'); }),
               axisLabel: { width: labelW, overflow: 'truncate', fontFamily: SANS, fontSize: 12, interval: 0, margin: 10 } },
      tooltip: tip(L, { trigger: 'item', formatter: function (q) {
        var v = q.data;
        if (v.r) return v.code + ': Class I recall event ' + v.r.event + ' initiated ' + v.r.date + '<br>root cause as recorded: ' + (v.r.rootCause || 'not recorded');
        if (v.e && v.u) return v.code + ': ' + monthShort(v.e.start) + ' to ' + monthShort(v.e.end) + ' (' + v.e.months + ' months) would be an episode if the rule were on; it opens nothing';
        if (v.e) return v.code + ': episode ' + monthShort(v.e.start) + ' to ' + monthShort(v.e.end) + ' (' + v.e.months + ' months), largest excess ' + nf(v.e.excess) + ' reports';
        return v.code + ': ' + monthShort(v.month) + ' flagged. ' + d.rule;
      } }),
      series: [
        // Episodes as bars drawn with the custom renderer across their months, under the marks.
        { name: 'Episodes', type: 'custom', data: epData, z: 2,
          renderItem: function (params, api) {
            var s = api.coord([api.value(0), api.value(1)]), e = api.coord([api.value(2), api.value(1)]);
            var half = api.size([1, 1])[0] / 2, h = Math.max(10, api.size([1, 1])[1] * 0.42);
            var u = epData[params.dataIndex].u;
            // Filled with an outline for an episode in the queue (the outline keeps it in grayscale); outline only
            // for one the rule would open if it were on.
            return { type: 'rect', shape: { x: s[0] - half, y: s[1] - h / 2, width: (e[0] - s[0]) + 2 * half, height: h },
                     style: u ? { fill: 'rgba(0,0,0,0)', stroke: INK.madrona, lineWidth: 1.5 }
                              : { fill: alpha(C.madrona, 0.35), stroke: INK.madrona, lineWidth: 1 } };
          } },
        { name: 'Flagged months', type: 'scatter', data: flagData, symbolSize: L.narrow ? 6 : 9, symbol: 'rect', itemStyle: { color: C.madrona }, z: 3 },
        { name: 'Class I recall initiations', type: 'scatter', data: recData, symbolSize: L.narrow ? 8 : 11, symbol: 'diamond',
          itemStyle: { color: C.paper, borderColor: INK.madrona, borderWidth: 1.5 }, z: 4 }
      ]
    };
    var ep = d.episodeNote, ix = ep ? idx[ep.end] : n - 1;
    if (L.narrow && ep) {
      option.series[1].markPoint = { symbol: 'circle', symbolSize: 0, data: [{ coord: [ix, lanes.findIndex(function (l) { return l.code === ep.code; })],
        label: { show: true, formatter: ep.label, position: 'top', distance: Math.round(laneH / 2 + 2), color: INK.madrona,
                 fontFamily: SERIF, fontSize: 12, align: ix > n / 2 ? 'right' : 'left' } }] };
    }
    if (!L.narrow) {
      // The annotation names the episode the title counts (or the absence of one). It sits in headroom reserved
      // above the first lane (K3) and is aligned to the episode's last month; the text names the lane.
      option.series[1].markPoint = annotation(d.annotation, {
        color: ep ? C.madrona : C.slateMoss, coord: [ix, 0], position: 'top', distance: Math.round(laneH / 2 + 6),
        align: ix > n / 2 ? 'right' : 'left', width: Math.min(340, Math.round(L.w * 0.5)), container: L.w, fontSize: 12
      });
    }
    ch.setOption(option);
    // The key under the plot (3.6: a legend only where direct labels cannot sit; three mark types in one lane) is
    // written into the card by build_page.py (Build Brief 2.2 step 8); it was composed here, against K2.
    return finish(host, ch, {
      provenance: d.provenance, summary: d.summary, ariaLabel: d.ariaLabel, noteVisible: L.narrow,
      nav: { chart: ch, label: d.ariaLabel, series: lanes.map(function (l, li) {
        var pts = [];
        l.flagged.forEach(function (m) { pts.push({ label: monthShort(m), value: 'flagged', seriesIndex: 1, dataIndex: flagData.findIndex(function (f) { return f.code === l.code && f.month === m; }) }); });
        l.classI.forEach(function (r) { pts.push({ label: r.date, value: 'Class I recall initiated, event ' + r.event, seriesIndex: 2, dataIndex: recData.findIndex(function (f) { return f.code === l.code && f.r.event === r.event; }) }); });
        return { name: l.code + (l.enabled ? '' : ' (rule disabled)'),
                 summary: plural(l.flagged.length, 'flagged month') + ', ' + plural(l.episodes.length, 'episode') +
                          (l.enabled ? '' : ' (' + l.ungated.length + ' if the rule were on)') + ', ' + plural(l.classI.length, 'Class I initiation'),
                 points: pts.length ? pts : [{ label: 'none', value: 'no flags, no episodes, no Class I initiation', seriesIndex: 1, dataIndex: 0 }] };
      }) }
    }, L);
  });

  /* ================= c5 · how complete is the recent record ================= */
  mount('c5', function (host, L) {
    var d = D.c5, n = d.months.length;
    var tb = titleBlock(L, d.finding, d.subtitle), top = tb.top;
    var endLabelW = gutter(['within 12 months', 'within 6', 'within 3'], L);
    var plotW = Math.max(160, L.w - 70 - endLabelW);
    var plotH = cascadiaBankedHeight(d.within12, plotW, { min: 220, max: 340 }) || 280;
    host.style.height = (top + plotH + 60) + 'px';
    var ax = niceAxis(Math.max.apply(null, d.within12), 1.15, 7);
    var i12 = d.months.indexOf(d.incomplete12[0]);
    var i3 = d.months.indexOf(d.incomplete3[0]);
    var ch = echarts.init(host, 'cascadia');
    var option = {
      title: tb.title,
      grid: { left: 8, right: endLabelW + 8, top: top, height: plotH, containLabel: true },
      xAxis: { type: 'category', data: d.months.map(function (m) { return monthTick(m, L.narrow); }), boundaryGap: false,
               axisLabel: axisLabelX(L, n, plotW), axisTick: { show: false } },
      yAxis: { type: 'value', min: 0, max: ax.max, interval: ax.interval, name: 'reports by event month', nameLocation: 'end', nameGap: 8,
               nameTextStyle: { color: C.slateMoss, fontFamily: SANS, fontSize: 12, align: 'left' },
               axisLabel: { formatter: function (v) { return v >= 1000 ? (v / 1000) + 'K' : String(v); } } },
      tooltip: tip(L, { trigger: 'axis', formatter: function (qs) {
        var i = qs[0].dataIndex;
        return monthShort(d.months[i]) + ' events<br>received within 3 months: ' + nf(d.within3[i]) + '<br>within 6: ' + nf(d.within6[i]) +
               '<br>within 12: ' + nf(d.within12[i]) +
               (d.incomplete3.indexOf(d.months[i]) >= 0 ? '<br>every window still filling' :
                d.incomplete6.indexOf(d.months[i]) >= 0 ? '<br>6- and 12-month windows still filling' :
                d.incomplete12.indexOf(d.months[i]) >= 0 ? '<br>12-month window still filling' : '');
      } }),
      series: [
        { name: 'within 12 months', type: 'line', data: d.within12, showSymbol: false, symbol: 'none',
          lineStyle: { color: C.rain, width: 2, type: [10, 5] }, itemStyle: { color: C.rain }, z: 2,
          endLabel: endLabel('within 12 months', L, C.slateMoss),
          markArea: { silent: true, itemStyle: { color: C.mist, opacity: 0.6 },
                      // Two shadings: the last 12 months, and over them the last 3, where every window is still filling.
                      data: [[{ xAxis: i12 }, { xAxis: n - 1 }], [{ xAxis: i3 }, { xAxis: n - 1 }]] } },
        { name: 'within 6 months', type: 'line', data: d.within6, showSymbol: false, symbol: 'none',
          lineStyle: { color: C.rain, width: 2, type: [3, 4] }, itemStyle: { color: C.rain }, z: 3,
          endLabel: endLabel('within 6', L, C.slateMoss) },
        { name: 'within 3 months', type: 'line', data: d.within3, showSymbol: false, symbol: 'none',
          lineStyle: { color: C.evergreen, width: 2.5 }, itemStyle: { color: C.evergreen }, z: 4,
          endLabel: endLabel('within 3', L, INK.evergreen) }
      ]
    };
    var mp = L.narrow ? { symbol: 'circle', symbolSize: 0, data: [] } : annotation(d.annotation, {
      color: C.evergreen, coord: [n - 1, ax.max], position: 'bottom', distance: 6, align: 'right',
      width: Math.min(240, Math.round(plotW * 0.45)), container: L.w
    });
    // The two months the title compares, marked on the like-for-like line with their values (Rule 3.2);
    // subordinate to the annotation. At the narrow width the month is dropped from the label, a declared abbreviation.
    if (d.compare) {
      d.compare.months.forEach(function (m, k) {
        var i = d.months.indexOf(m);
        if (i < 0 || d.compare.values[k] == null) return;
        mp.data.push({ coord: [i, d.compare.values[k]], symbol: 'circle', symbolSize: 7, itemStyle: { color: C.evergreen },
                       label: { show: true, formatter: L.narrow ? nf(d.compare.values[k]) : monthShort(m) + ': ' + nf(d.compare.values[k]),
                                position: 'bottom', distance: 16, color: INK.evergreen, fontFamily: SANS, fontSize: 12, align: k ? 'right' : 'center' } });
      });
    }
    option.series[2].markPoint = mp;
    ch.setOption(option);
    {
      spreadEndLabels(ch, [
        { seriesIndex: 0, dataIndex: n - 1, value: d.within12[n - 1] },
        { seriesIndex: 1, dataIndex: n - 1, value: d.within6[n - 1] },
        { seriesIndex: 2, dataIndex: n - 1, value: d.within3[n - 1] }
      ], 15);
    }
    return finish(host, ch, {
      provenance: d.provenance, summary: d.summary, ariaLabel: d.ariaLabel,
      nav: { chart: ch, label: d.ariaLabel, series: [
        { name: 'Received within 3 months', summary: 'the like-for-like series', points: d.months.map(function (m, i) { return { label: monthShort(m), value: nf(d.within3[i]), seriesIndex: 2, dataIndex: i }; }) },
        { name: 'Received within 6 months', summary: 'context', points: d.months.map(function (m, i) { return { label: monthShort(m), value: nf(d.within6[i]), seriesIndex: 1, dataIndex: i }; }) },
        { name: 'Received within 12 months', summary: 'context; the last ' + d.incomplete12.length + ' months are still filling', points: d.months.map(function (m, i) { return { label: monthShort(m), value: nf(d.within12[i]), seriesIndex: 0, dataIndex: i }; }) }
      ] }
    }, L);
  });

})();
