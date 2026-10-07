"""build_page.py -- docs/index.html from the conformed tables only. Offline.

Every figure and every sentence a chart shows is composed HERE, from
data/conformed/ and config/model.json, and passed to docs/assets/page.js in
the data block between the CASCADIA_DATA markers; page.js decides geometry
only (CHART-REVIEW K2: every figure traces to a build step, none is typed).

Chrome follows the Felix design system v1.0 @ 1a41a5e by pointer (D14): the
class strings are Felix's own, compiled by the Tailwind CLI into
docs/assets/felix.css, with the 6a contrast substitutions (ink-soft where
Felix shows muted below 0.875rem; white/60 where it shows white/40 or
white/35) and the 6b Google Fonts load. Charts follow VIZ-PRINCIPLES v2.8
(D15) and nothing of Felix reaches inside a canvas.

Five charts:
  c1  the outlook: the headline code's monthly series with the model in use's
      one-month-ahead points over the evaluated months, and the next month as
      a quantile dotplot (Rule 4.5)
  c2  the test: locked-period actuals against the candidate and baseline A,
      the model in use's 80% range, and the largest miss annotated
  c3  did the ranges hold: 80% coverage in the locked test per code
  c4  what deserves review: flagged months, episodes and Class I initiations
      on one timeline, 2024-01 to 2026-08, all seven codes
  c5  how complete is the recent record: the headline code's event-month
      counts at 3, 6 and 12 months of receipt lag (M-02)

    python src/build_page.py
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import pathlib
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from forecast import add_months, months_between  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
CONF = REPO / "data" / "conformed"
REF = REPO / "data" / "reference"
GOV = REPO / "governance"
DOCS = REPO / "docs"
CONFIG = REPO / "config" / "model.json"

PAGE_URL = "https://www.robbinsanalytics.com/cascadia-early-warning/"
SITE_URL = "https://www.robbinsanalytics.com/"
CASE_URL = "https://www.robbinsanalytics.com/projects/cascadia-early-warning.html"
REPO_URL = "https://github.com/RobbinsAnalytics/cascadia-early-warning"
THUMB_URL = "https://www.robbinsanalytics.com/assets/thumb-early-warning.png"
SOURCE = "openFDA device event, recall and enforcement endpoints"
AS_OF = "2026-08-31"
RETRIEVED = "2026-10-06"
LAST_UPDATED = "2026-09-29"
DISCLAIMER = ("Report counts are not incident rates or measures of device safety. This independent "
              "public-data demonstration provides no medical, legal or regulatory advice.")
EVAL_START, EVAL_END = "2024-01", "2026-08"
SERIES_START = "2022-01"
DOT_N = 20


def read_csv(name: str, folder: pathlib.Path = CONF) -> list[dict]:
    with (folder / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def nf(n) -> str:
    return format(int(round(float(n))), ",")


def pct(x, dp=0) -> str:
    return ("%." + str(dp) + "f%%") % (100 * float(x))


def month_name(ym: str) -> str:
    names = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]
    return "%s %s" % (names[int(ym[5:7]) - 1], ym[:4])


def month_short(ym: str) -> str:
    return "%s %s" % (["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(ym[5:7]) - 1], ym[:4])


def git_short(path: str) -> str:
    r = subprocess.run(["git", "log", "-1", "--format=%h", "--", path], cwd=REPO, capture_output=True, text=True)
    return r.stdout.strip() or "uncommitted"


def asset_v(name: str) -> str:
    b = (DOCS / "assets" / name).read_bytes()
    return "assets/%s?v=%s" % (name, hashlib.md5(b).hexdigest()[:10])


def no_sep(s: str, what: str) -> str:
    if "·" in s:
        raise SystemExit("provenance %s contains the strip separator (K5): %r" % (what, s))
    return s


def words(s: str) -> int:
    return len(s.split())


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def load():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    d = {
        "cfg": cfg,
        "m01": read_csv("monthly_report_count.csv"),
        "m02": read_csv("monthly_lag_matched.csv"),
        "lag_summary": read_csv("lag_summary.csv"),
        "fc": read_csv("forecast.csv"),
        "scored": read_csv("forecast_scored.csv"),
        "scores": read_csv("forecast_score.csv"),
        "queue": [q for q in read_csv("review_queue.csv") if q["product_code"]],
        "work": read_csv("review_workload.csv"),
        "recall": read_csv("recall_context.csv"),
        "recall_count": json.loads((CONF / "recall_count.json").read_text(encoding="utf-8")),
        "recall_meta": json.loads((CONF / "recall_context_meta.json").read_text(encoding="utf-8")),
        "codes": read_csv("product_code.csv"),
        "gate": read_csv("cohort_gate.csv"),
        "receipt": read_csv("exclusion_receipt.csv"),
        "quarantine": read_csv("quarantine.csv"),
        "remedial": read_csv("monthly_remedial_recall.csv"),
        "known": read_csv("known_events.csv", REF),
    }
    d["forecast_codes"] = [g["product_code"] for g in d["gate"] if g["forecast"] == "true"]
    d["names"] = {c["product_code"]: c["device_name"] for c in d["codes"]}
    d["eligible"] = {(r["product_code"], r["month"]): int(r["eligible_reports"]) for r in d["m01"]}
    d["in_use"] = {c: cfg["promoted"][c]["model_in_use"] for c in d["forecast_codes"]}
    return d


def model_label(m: str) -> str:
    return {"baseline_a": "trailing three-month mean", "baseline_b": "same month last year",
            "candidate": "ETS candidate"}[m]


def headline_code(d) -> str:
    """Deterministic, and stated on the page: among the codes whose review
    rule is enabled (locked-test 80% coverage at or above 70%), the
    largest-volume code (eligible reports over the last twelve elapsed months)
    for which the candidate earned use; if the candidate earned use on none
    of them, the largest-volume enabled code; if no code is enabled, the
    largest-volume code of all."""
    last12 = [add_months(AS_OF[:7], -k) for k in range(12)]
    vol = {c: sum(d["eligible"].get((c, m), 0) for m in last12) for c in d["forecast_codes"]}
    enabled = [w["product_code"] for w in d["work"] if w["rule_enabled"] == "true" and w["product_code"] in d["forecast_codes"]]
    cand = [c for c in enabled if d["in_use"][c] == "candidate"]
    pool = cand or enabled or d["forecast_codes"]
    return max(pool, key=lambda c: (vol[c], c))


def fc_rows(d, code, model, h, period=None):
    rows = [r for r in d["fc"] if r["product_code"] == code and r["model"] == model and r["horizon"] == str(h)
            and (period is None or r["period"] == period)]
    return sorted(rows, key=lambda r: r["target"])


def score_cell(d, code, model, h, period):
    for r in d["scores"]:
        if (r["product_code"], r["model"], r["horizon"], r["period"]) == (code, model, str(h), period):
            return r
    return None


def error_quantiles(d, code, model, h, origin, n_dots=DOT_N):
    """The 36 latest elapsed signed errors at the origin, as n_dots quantiles
    (the predictive distribution's discrete outcomes for Rule 4.5). Same
    window as forecast.py and validate_measures.py."""
    rows = [r for r in d["fc"] if r["product_code"] == code and r["model"] == model and r["horizon"] == str(h)
            and r["point"] != "" and r["target"] <= origin]
    errs = []
    for r in sorted(rows, key=lambda r: r["target"]):
        y = d["eligible"].get((code, r["target"]))
        if y is not None:
            errs.append(y - float(r["point"]))
    errs = errs[-36:]
    qs = [(i - 0.5) / n_dots for i in range(1, n_dots + 1)]
    return [float(v) for v in np.quantile(np.asarray(errs), qs)], len(errs)


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------

def chart1(d, code):
    use = d["in_use"][code]
    months = [m for m in sorted({r["month"] for r in d["m01"] if r["product_code"] == code}) if m >= SERIES_START]
    actual = [d["eligible"][(code, m)] for m in months]
    pts = {r["target"]: r for r in fc_rows(d, code, use, 1) if r["period"] in ("locked", "recent", "outlook")}
    points = [None if m not in pts else float(pts[m]["point"]) for m in months]
    lo80 = [None if m not in pts or pts[m]["lower80"] == "" else float(pts[m]["lower80"]) for m in months]
    hi80 = [None if m not in pts or pts[m]["upper80"] == "" else float(pts[m]["upper80"]) for m in months]
    outlook = fc_rows(d, code, use, 1, "outlook")[0]
    o_target = outlook["target"]
    o_point = float(outlook["point"])
    o_lo80, o_hi80 = float(outlook["lower80"]), float(outlook["upper80"])
    o_lo50, o_hi50 = float(outlook["lower50"]), float(outlook["upper50"])
    qerr, n_err = error_quantiles(d, code, use, 1, outlook["origin"])
    dots = [max(0.0, o_point + e) for e in qerr]
    last_actual = actual[-1]
    finding = ("%s: expect about %s reports in %s, with an 80%% range of %s to %s"
               % (code, nf(o_point), month_name(o_target), nf(o_lo80), nf(o_hi80)))
    subtitle = ("Eligible reports received per month for %s (%s), %s to %s, with the %s's one-month-ahead points and 80%% range over the "
                "evaluated months. The %s figure is an elapsed-period estimate: issued %s, after the month ended "
                "and before the source loaded it." % (code, d["names"].get(code, ""), month_short(months[0]), month_short(months[-1]),
                                                       model_label(use), month_short(o_target), RETRIEVED))
    annotation = "point %s is the tick; filled dots span the 80%% range, %s to %s" % (nf(o_point), nf(o_lo80), nf(o_hi80))
    removed = sum(int(r["reports_matched"]) for r in d["receipt"] if r["field"] == "ANY (reports removed)")
    countable = sum(int(r["reports_matched"]) for r in d["receipt"] if r["field"] == "ALL (countable reports)")
    summary = ("Line chart of eligible reports received per month for product code %s from %s to %s, %d months, "
               "range %s to %s, latest %s in %s. A dashed line carries the %s's one-month-ahead point for each month "
               "from %s, with a shaded band for its 80%% range. At the right, %d dots show the next month, %s: point %s, 50%% range %s to %s, 80%% range %s to %s, "
               "from %d past errors."
               % (code, month_short(months[0]), month_short(months[-1]), len(months), nf(min(actual)), nf(max(actual)),
                  nf(last_actual), month_short(months[-1]), model_label(use), month_short(min(pts)) if pts else "n/a",
                  DOT_N, month_short(o_target), nf(o_point), nf(o_lo50), nf(o_hi50), nf(o_lo80), nf(o_hi80), n_err))
    table = [[month_short(m), nf(a), "" if p is None else nf(p), "" if lo is None else nf(lo), "" if hi is None else nf(hi)]
             for m, a, p, lo, hi in zip(months, actual, points, lo80, hi80)]
    table.append([month_short(o_target), "not yet in the source", nf(o_point), nf(o_lo80), nf(o_hi80)])
    return {
        "code": code, "model": use, "modelLabel": model_label(use),
        "months": months, "actual": actual, "points": points, "lo80": lo80, "hi80": hi80,
        "outlook": {"target": o_target, "point": o_point, "lo50": o_lo50, "hi50": o_hi50,
                    "lo80": o_lo80, "hi80": o_hi80, "dots": dots, "nErrors": n_err},
        "finding": finding, "subtitle": subtitle, "annotation": annotation, "summary": summary,
        "ariaLabel": summary,
        "provenance": {"source": no_sep(SOURCE, "source"), "asOf": no_sep("receipts through " + AS_OF, "asOf"),
                       "flags": no_sep("counts, not rates; the firm-list exclusion removed %s of %s reports; next month is an elapsed-period estimate" % (nf(removed), nf(countable)), "flags")},
        "table": table,
    }


def chart2(d, code):
    use = d["in_use"][code]
    locked = fc_rows(d, code, use, 1, "locked")
    months = [r["target"] for r in locked]
    actual = [d["eligible"][(code, m)] for m in months]
    cand = {r["target"]: float(r["point"]) for r in fc_rows(d, code, "candidate", 1, "locked")}
    base = {r["target"]: float(r["point"]) for r in fc_rows(d, code, "baseline_a", 1, "locked")}
    lo80 = [float(r["lower80"]) for r in locked]
    hi80 = [float(r["upper80"]) for r in locked]
    sc_c = score_cell(d, code, "candidate", 1, "locked")
    sc_a = score_cell(d, code, "baseline_a", 1, "locked")
    sc_use = score_cell(d, code, use, 1, "locked")
    errs = [abs(a - (cand if use == "candidate" else base)[m]) for a, m in zip(actual, months)]
    i_miss = max(range(len(errs)), key=lambda i: (errs[i], -i))   # deterministic: largest, earliest on a tie
    miss_m = months[i_miss]
    miss_pt = (cand if use == "candidate" else base)[miss_m]
    better = float(sc_c["mae"]) < float(sc_a["mae"])
    outside = [{"month": m, "actual": a} for m, a, lo, hi in zip(months, actual, lo80, hi80) if a < lo or a > hi]
    n_in = len(months) - len(outside)
    if use == "candidate":
        finding = ("On the locked test the candidate's 80%% range held %d of %d %s months; its average miss was %s reports a month, against the trailing mean's %s"
                   % (n_in, len(months), code, nf(sc_use["mae"]), nf(sc_a["mae"])))
    else:
        finding = ("On the locked test the trailing mean's 80%% range held %d of %d %s months; its average miss was %s reports a month; the candidate missed by %s and was not promoted"
                   % (n_in, len(months), code, nf(sc_a["mae"]), nf(sc_c["mae"])))
    subtitle = ("One-month-ahead points from both models against what arrived, %s to %s, %d locked months; the band is the %s's 80%% range, "
                "which covered %s of these months; rings mark the %d months it did not. The review rule flags a month above the band by "
                "five or more reports. Selection was frozen at 2023-12 and this test ran once."
                % (month_short(months[0]), month_short(months[-1]), len(months), model_label(use), pct(sc_use["coverage80"]), len(outside)))
    annotation = "largest miss: %s, %s arrived against %s expected" % (month_short(miss_m), nf(actual[i_miss]), nf(miss_pt))
    summary = ("Line chart over the %d locked-test months %s to %s for product code %s. Actual reports range %s to %s. The %s's "
               "points carry a mean absolute error of %s and its 80%% range covered %s of months (mean width %s); the %s's mean "
               "absolute error is %s. The largest miss of the model in use is %s: %s actual against %s expected."
               % (len(months), month_short(months[0]), month_short(months[-1]), code, nf(min(actual)), nf(max(actual)),
                  model_label(use), nf(sc_use["mae"]), pct(sc_use["coverage80"]), nf(sc_use["width80"]),
                  model_label("baseline_a" if use == "candidate" else "candidate"),
                  nf(sc_a["mae"] if use == "candidate" else sc_c["mae"]), month_short(miss_m), nf(actual[i_miss]), nf(miss_pt)))
    table = [[month_short(m), nf(a), nf(cand[m]), nf(base[m]), nf(lo), nf(hi)]
             for m, a, lo, hi in zip(months, actual, lo80, hi80)]
    return {
        "code": code, "model": use, "modelLabel": model_label(use), "months": months, "actual": actual, "outside": outside,
        "candidate": [cand[m] for m in months], "baselineA": [base[m] for m in months], "lo80": lo80, "hi80": hi80,
        "miss": {"month": miss_m, "index": i_miss, "actual": actual[i_miss], "point": miss_pt},
        "scores": {"use": {k: float(sc_use[k]) for k in ("mae", "coverage80", "width80", "wis")},
                   "candidate": {k: float(sc_c[k]) for k in ("mae", "coverage80", "width80", "wis")},
                   "baselineA": {k: float(sc_a[k]) for k in ("mae", "coverage80", "width80", "wis")}},
        "candidateBetter": better,
        "finding": finding, "subtitle": subtitle, "annotation": annotation, "summary": summary, "ariaLabel": summary,
        "provenance": {"source": no_sep(SOURCE, "source"), "asOf": no_sep("receipts through " + AS_OF, "asOf"),
                       "flags": no_sep("counts, not rates; locked test 2024-01 to 2025-12, selection frozen 2023-12, run once", "flags")},
        "table": table,
    }


def chart3(d):
    rows = []
    for code in d["forecast_codes"]:
        use = d["in_use"][code]
        sc = score_cell(d, code, use, 1, "locked")
        w = next(x for x in d["work"] if x["product_code"] == code)
        rows.append({"code": code, "model": use, "modelLabel": model_label(use),
                     "coverage80": float(sc["coverage80"]), "n": int(sc["n"]), "inside": int(round(float(sc["coverage80"]) * int(sc["n"]))),
                     "enabled": w["rule_enabled"] == "true", "name": d["names"].get(code, "")})
    rows.sort(key=lambda r: (-r["coverage80"], r["code"]))
    lo, hi = min(rows, key=lambda r: r["coverage80"]), max(rows, key=lambda r: r["coverage80"])
    n_dis = sum(1 for r in rows if not r["enabled"])
    finding = ("The 80%% ranges covered between %s and %s of locked-test months across the seven codes; %s"
               % (pct(lo["coverage80"]), pct(hi["coverage80"]),
                  "every code keeps its review rule" if n_dis == 0 else
                  "%d code%s below 70%% %s the review rule disabled" % (n_dis, "" if n_dis == 1 else "s", "has" if n_dis == 1 else "have")))
    subtitle = ("Share of the %d locked-test months (2024-01 to 2025-12) whose actual fell inside the model in use's 80%% range, "
                "horizon one, by code; nominal 80%%. The numbers gate expected 60%% to 95%% (the shaded band) and disables the rule below "
                "70%%; both were written before the test ran. The row label names the model in use: the ETS candidate where it earned use, "
                "else the trailing mean." % rows[0]["n"])
    annotation = "dashed: 80% nominal and 70% disable; shaded: gate band; orange: rule off"
    summary = ("Horizontal bar chart of 80%% range coverage in the locked test for %d product codes, sorted from highest to lowest: %s. "
               "Nominal coverage is 80%%; the disable line is 70%%; %d code%s disabled."
               % (len(rows), "; ".join("%s %s" % (r["code"], pct(r["coverage80"])) for r in rows), n_dis, "" if n_dis == 1 else "s"))
    table = [[r["code"], r["name"], r["modelLabel"], pct(r["coverage80"], 1), str(r["n"]), "yes" if r["enabled"] else "no"] for r in rows]
    return {"rows": rows, "finding": finding, "subtitle": subtitle, "annotation": annotation, "summary": summary,
            "ariaLabel": summary,
            "provenance": {"source": no_sep(SOURCE, "source"), "asOf": no_sep("receipts through " + AS_OF, "asOf"),
                           "flags": no_sep("not a safety measure; coverage inclusive at the bound; empirical ranges from 36 errors", "flags")},
            "table": table}


def chart4(d):
    months = [add_months(EVAL_START, k) for k in range(months_between(EVAL_START, EVAL_END) + 1)]
    lanes = []
    for code in d["forecast_codes"]:
        use = d["in_use"][code]
        flagged = []
        for r in d["scored"]:
            if r["product_code"] == code and r["model"] == use and r["horizon"] == "1" and r["period"] in ("locked", "recent"):
                if float(r["actual"]) > float(r["upper80"]) and float(r["actual"]) - float(r["point"]) >= 5:
                    flagged.append(r["target"])
        eps = [{"start": q["episode_start"], "end": q["episode_end"], "months": int(q["months_in_episode"]),
                "excess": float(q["max_excess_over_point"]), "status": q["status"]}
               for q in d["queue"] if q["product_code"] == code]
        rec = []
        for r in d["recall"]:
            if code in r["product_codes"].split("|") and "Class I" in r["classification"].split("|") and r["event_date_initiated"][:7] >= EVAL_START:
                rec.append({"month": r["event_date_initiated"][:7], "date": r["event_date_initiated"], "event": r["res_event_number"],
                            "rootCause": r["root_cause"]})
        w = next(x for x in d["work"] if x["product_code"] == code)
        lanes.append({"code": code, "name": d["names"].get(code, ""), "model": use, "enabled": w["rule_enabled"] == "true",
                      "flagged": sorted(flagged), "episodes": eps, "classI": sorted(rec, key=lambda r: r["date"])})
    # Lanes with the rule on first, each group by flagged months (Rule 2.7: a declared order, stated in the subtitle).
    lanes.sort(key=lambda l: (not l["enabled"], -len(l["flagged"]), l["code"]))
    n_off = sum(1 for l in lanes if not l["enabled"])
    n_off_flags = sum(len(l["flagged"]) for l in lanes if not l["enabled"])
    rc = d["recall_count"]
    rc_init = int(rc["class_i_initiations_in_evaluated_span_by_forecast_code"])
    rc_prec = int(rc["class_i_initiations_preceded_by_an_episode_start"])
    n_ep = sum(len(l["episodes"]) for l in lanes)
    n_fl = sum(len(l["flagged"]) for l in lanes)
    n_rec = sum(len(l["classI"]) for l in lanes)
    eval_months = sum(int(w["evaluated_months"]) for w in d["work"])
    rate = n_ep / eval_months if eval_months else 0.0
    if n_ep == 0:
        finding = ("The review rule opened no episode in %d evaluated months across seven codes; %d single months were flagged and %d Class I recall%s began in the span"
                   % (eval_months, n_fl, n_rec, "" if n_rec == 1 else "s"))
    else:
        finding = ("The review rule opened %d episode%s in %d evaluated months across seven codes, %.3f per month; %d Class I recall%s began in the span"
                   % (n_ep, "" if n_ep == 1 else "s", eval_months, rate, n_rec, "" if n_rec == 1 else "s"))
    subtitle = ("One lane per code, %s to %s; lanes with the rule on come first, each group ordered by flagged months. A filled square is a "
                "month whose actual exceeded the 80%% range by five or more reports (the rule is one-sided by design); a hollow square is the "
                "same in a lane with the rule off, where it opens no episode; a bar is an episode of two or more consecutive filled squares; "
                "a diamond, raised above the lane, is the firm-initiated date of a Class I recall event in that code, same-month events side "
                "by side. %d of the %d flagged months fall in the %d lanes with the rule off. Of the %d Class I initiations, %d were preceded "
                "by an episode start. Association only: the timeline is context, not validation. FDA's 2024-08-29 summary-reporting change "
                "does not apply to these codes."
                % (month_short(EVAL_START), month_short(EVAL_END), n_off_flags, n_fl, n_off, rc_init, rc_prec))
    # The annotation names the episode the title counts; with none, it says so (Rule 3.4: at the mark the claim depends on).
    ep_note, best = None, None
    for l in lanes:
        for e in l["episodes"]:
            if best is None or e["excess"] > best[1]["excess"]:
                best = (l, e)
    if best:
        l, e = best
        peak = max((r for r in d["scored"] if r["product_code"] == l["code"] and r["model"] == l["model"] and r["horizon"] == "1"
                    and e["start"] <= r["target"] <= e["end"]), key=lambda r: float(r["actual"]) - float(r["point"]))
        ep_note = {"code": l["code"], "start": e["start"], "end": e["end"], "actual": float(peak["actual"]), "point": float(peak["point"])}
        annotation = ("%s episode: %s, %s to %s, %s arrived against %s expected"
                      % ("the one" if n_ep == 1 else "largest", l["code"], month_short(e["start"]), month_short(e["end"]),
                         nf(ep_note["actual"]), nf(ep_note["point"])))
    else:
        annotation = "no two consecutive flagged months in any lane; the review queue is empty"
    summary = ("Timeline chart with %d lanes, one per product code, over %d months from %s to %s. Flagged months: %d in total (%s). "
               "Episodes: %d. Class I recall initiations in the span: %d (%s)."
               % (len(lanes), len(months), month_short(EVAL_START), month_short(EVAL_END), n_fl,
                  "; ".join("%s %d" % (l["code"], len(l["flagged"])) for l in lanes) or "none", n_ep, n_rec,
                  "; ".join("%s %s" % (l["code"], ", ".join(r["month"] for r in l["classI"])) for l in lanes if l["classI"]) or "none"))
    table = []
    for l in lanes:
        table.append([l["code"], l["name"], l["modelLabel"] if "modelLabel" in l else model_label(l["model"]),
                      "yes" if l["enabled"] else "no", str(len(l["flagged"])), ", ".join(month_short(m) for m in l["flagged"]) or "none",
                      "; ".join("%s to %s (%d)" % (month_short(e["start"]), month_short(e["end"]), e["months"]) for e in l["episodes"]) or "none",
                      ", ".join("%s (event %s)" % (r["date"], r["event"]) for r in l["classI"]) or "none"])
    return {"months": months, "lanes": lanes, "episodes": n_ep, "flagged": n_fl, "classI": n_rec, "evaluatedMonths": eval_months,
            "rate": rate, "episodeNote": ep_note, "finding": finding, "subtitle": subtitle, "annotation": annotation, "summary": summary, "ariaLabel": summary,
            "provenance": {"source": no_sep(SOURCE, "source"), "asOf": no_sep("receipts through " + AS_OF, "asOf"),
                           "flags": no_sep("counts and dates, not rates or risk; class from the enforcement endpoint; events deduplicated on event number", "flags")},
            "table": table}


def chart5(d, code):
    rows = sorted([r for r in d["m02"] if r["product_code"] == code and r["event_month"] >= SERIES_START], key=lambda r: r["event_month"])
    months = [r["event_month"] for r in rows]
    w3 = [int(r["within_3"]) for r in rows]
    w6 = [int(r["within_6"]) for r in rows]
    w12 = [int(r["within_12"]) for r in rows]
    tot = [int(r["reports_with_event_month"]) for r in rows]
    last = AS_OF[:7]
    incomplete3 = [m for m in months if months_between(m, last) < 3]
    incomplete12 = [m for m in months if months_between(m, last) < 12]
    ls = next(x for x in d["lag_summary"] if x["product_code"] == code)
    # the like-for-like comparison: the 3-month line's latest complete month against the same line a year earlier
    comp = [m for m in months if m not in incomplete3]
    m_last, m_prev = comp[-1], add_months(comp[-1], -12)
    v_last = w3[months.index(m_last)]
    v_prev = w3[months.index(m_prev)] if m_prev in months else None
    finding = ("%s event months are compared like for like: %s had %s reports within three months, against %s for %s"
               % (code, month_short(m_last), nf(v_last), nf(v_prev) if v_prev is not None else "n/a", month_short(m_prev)))
    subtitle = ("Reports by the month the event happened, counted only if received within 3, 6 or 12 months of it, %s to %s. "
                "Shaded months are still filling: the darker shade is the last 3 months, where every window is incomplete; the lighter is "
                "the last 12, where only the 12-month figure is (%d months). %s of this code's eligible reports carry no event date; they "
                "are counted in charts 1 to 4 by receipt month and are left out here only."
                % (month_short(months[0]), month_short(months[-1]), len(incomplete12), nf(ls["missing_event_date"])))
    annotation = "darker shade: all three windows still filling; lighter: only the 12-month one"
    summary = ("Line chart with three series over event months %s to %s for product code %s: reports received within 3 months (range %s to %s), "
               "within 6 months (%s to %s) and within 12 months (%s to %s). Reports with an event month in the span: %s. Missing event date: %s. "
               "Negative lag: %s."
               % (month_short(months[0]), month_short(months[-1]), code, nf(min(w3)), nf(max(w3)), nf(min(w6)), nf(max(w6)),
                  nf(min(w12)), nf(max(w12)), nf(sum(tot)), nf(ls["missing_event_date"]), nf(ls["negative_lag"])))
    table = [[month_short(m), nf(t), nf(a), nf(b), nf(c), "yes" if m in incomplete12 else ""] for m, t, a, b, c in zip(months, tot, w3, w6, w12)]
    return {"code": code, "months": months, "within3": w3, "within6": w6, "within12": w12, "total": tot,
            "compare": ({"months": [m_prev, m_last], "values": [v_prev, v_last]} if v_prev is not None else None),
            "incomplete3": incomplete3, "incomplete12": incomplete12, "missingEventDate": int(ls["missing_event_date"]),
            "negativeLag": int(ls["negative_lag"]), "finding": finding, "subtitle": subtitle, "annotation": annotation,
            "summary": summary, "ariaLabel": summary,
            "provenance": {"source": no_sep(SOURCE, "source"), "asOf": no_sep("receipts through " + AS_OF, "asOf"),
                           "flags": no_sep("counts, not rates; lag is receipt month minus event month; diagnostic, not a nowcast", "flags")},
            "table": table}


# ---------------------------------------------------------------------------
# html helpers
# ---------------------------------------------------------------------------

def table(tid: str, caption: str, headers: list[str], rows: list[list[str]]) -> str:
    h = ['<div class="table-wrap"><table id="%s"><caption>%s</caption><thead><tr>' % (tid, html.escape(caption))]
    h += ['<th scope="col">%s</th>' % html.escape(c) for c in headers]
    h.append("</tr></thead><tbody>")
    for r in rows:
        h.append("<tr>" + "".join(
            '<th scope="row">%s</th>' % html.escape(str(c)) if i == 0 else "<td>%s</td>" % html.escape(str(c))
            for i, c in enumerate(r)) + "</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def chart_card(cid: str, index: str, kicker: str, height: int, note_class: str, note: str, tables: list[tuple[str, str]]) -> str:
    tbls = "".join('<details class="data-table rich"><summary>%s</summary>%s</details>' % (html.escape(label), t) for label, t in tables)
    return ('<div class="chart-card rounded-[1.75rem] bg-white p-5 sm:p-7" id="card-%s">'
            '<p class="font-mono text-[0.7rem] tracking-[0.16em] text-ink-soft uppercase">%s <span class="text-teal-2">%s</span></p>'
            '<p id="sum-%s" class="chart-summary"></p>'
            '<div id="%s" class="chart" style="height:%dpx"></div>'
            '<p id="note-%s" class="chart-note %s" hidden>%s</p>%s</div>'
            % (cid, index, html.escape(kicker), cid, cid, height, cid, note_class, html.escape(note), tbls))


def stat(index: str, value: str, label: str) -> str:
    return ('<div class="bg-white px-6 py-7"><p class="font-mono text-[0.7rem] text-ink-soft">%s</p>'
            '<p class="mt-3 font-display text-[2.4rem] leading-none font-bold tracking-[-0.04em] text-ink">%s</p>'
            '<p class="mt-2 max-w-[12rem] text-[0.8rem] leading-snug text-ink-soft">%s</p></div>' % (index, html.escape(value), html.escape(label)))


def main() -> int:
    d = load()
    code = headline_code(d)
    c1, c2, c3, c4, c5 = chart1(d, code), chart2(d, code), chart3(d), chart4(d), chart5(d, code)
    for c in (c1, c2, c3, c4, c5):
        if words(c["annotation"]) > 14:
            raise SystemExit("annotation over 14 words: %r" % c["annotation"])
        for k in ("source", "asOf", "flags"):
            no_sep(c["provenance"][k], k)
    cfg = d["cfg"]
    use = d["in_use"]
    n_cand = sum(1 for c in use.values() if c == "candidate")
    rc = d["recall_count"]
    rm = d["recall_meta"]
    total_eligible = sum(int(r["eligible_reports"]) for r in d["m01"])
    total_raw = sum(int(r["raw_reports"]) for r in d["m01"])
    excluded = sum(int(r["excluded_reports"]) for r in d["m01"])
    preregistration_commit = git_short("governance/pre-registration.md")
    model_commit = git_short("config/model.json")
    sha_local = ""
    rec_path = GOV / "exclusion-receipt-records.md"
    m = re.search(r"`([0-9a-f]{64})`", rec_path.read_text(encoding="utf-8")) if rec_path.exists() else None
    if m:
        sha_local = m.group(1)
    outlook_rows = []
    for c in d["forecast_codes"]:
        r = fc_rows(d, c, use[c], 1, "outlook")[0]
        outlook_rows.append([c, d["names"].get(c, ""), model_label(use[c]), month_short(r["target"]), nf(r["point"]),
                             nf(r["lower50"]), nf(r["upper50"]), nf(r["lower80"]), nf(r["upper80"]), r["calibration_n"]])
    score_rows = []
    for r in d["scores"]:
        if r["period"] in ("development", "locked", "recent") and r["horizon"] == "1":
            score_rows.append([r["product_code"], model_label(r["model"]), r["period"], r["n"], nf(r["mae"]),
                               r["mae_scaled_vs_a"][:5] if r["mae_scaled_vs_a"] else "", pct(r["coverage50"]), pct(r["coverage80"]),
                               nf(r["width80"]), ("%.1f" % float(r["wis"]))])
    queue_rows = [[q["product_code"], model_label(q["model_in_use"]), month_short(q["episode_start"]), month_short(q["episode_end"]),
                   q["months_in_episode"], q["max_excess_over_point"], q["status"]] for q in d["queue"]] or [["none", "", "", "", "", "", "the queue is empty"]]
    work_rows = [[w["product_code"], model_label(w["model_in_use"]), "yes" if w["rule_enabled"] == "true" else "no",
                  w["locked_coverage80"], w["evaluated_months"], w["flagged_months"], w["episodes"], w["episodes_per_evaluated_month"]]
                 for w in d["work"]]
    recall_rows = [[r["event_date_initiated"], r["product_codes"].replace("|", ", "), r["classification"].replace("|", ", ") or "not in enforcement",
                    r["enforcement_classification_date"] or "", r["root_cause"].replace("|", "; "), r["product_records"],
                    "yes" if r["reason_cites_reports"] == "true" else "no", r["res_event_number"]] for r in d["recall"]]
    gate_rows = [[g["product_code"], d["names"].get(g["product_code"], ""), g["complete_months_training"], nf(g["raw_training_reports"]),
                  nf(g["eligible_training_reports"]), "pass" if g["forecast"] == "true" else "fail"] for g in d["gate"]]
    receipt_rows = [[r["product_code"], r["field"], nf(r["reports_matched"])] for r in d["receipt"]]

    data = {"asOf": AS_OF, "retrieved": RETRIEVED, "lastUpdated": LAST_UPDATED, "source": SOURCE, "headline": code,
            "c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5": c5}
    f = {
        "headline": code, "headline_name": html.escape(d["names"].get(code, "")),
        "headline_rule": ("among the codes whose review rule is enabled, the largest-volume code for which the candidate earned use"
                          if any(d["in_use"][c] == "candidate" for c in d["forecast_codes"]) else
                          "the largest-volume code whose review rule is enabled; the candidate earned use nowhere"),
        "n_cand": str(n_cand), "n_codes": str(len(d["forecast_codes"])),
        "cand_codes": ", ".join(c for c in d["forecast_codes"] if use[c] == "candidate") or "none",
        "base_codes": ", ".join(c for c in d["forecast_codes"] if use[c] != "candidate") or "none",
        "o_target": month_name(c1["outlook"]["target"]), "o_point": nf(c1["outlook"]["point"]),
        "o_lo80": nf(c1["outlook"]["lo80"]), "o_hi80": nf(c1["outlook"]["hi80"]),
        "o_lo50": nf(c1["outlook"]["lo50"]), "o_hi50": nf(c1["outlook"]["hi50"]),
        "last_month": month_name(c1["months"][-1]), "last_actual": nf(c1["actual"][-1]),
        "c2_mae_use": nf(c2["scores"]["use"]["mae"]), "c2_mae_c": nf(c2["scores"]["candidate"]["mae"]), "c2_mae_a": nf(c2["scores"]["baselineA"]["mae"]),
        "c2_cov": pct(c2["scores"]["use"]["coverage80"]), "c2_miss_month": month_name(c2["miss"]["month"]),
        "c2_miss_actual": nf(c2["miss"]["actual"]), "c2_miss_point": nf(c2["miss"]["point"]),
        "c3_lo": pct(min(r["coverage80"] for r in c3["rows"])), "c3_hi": pct(max(r["coverage80"] for r in c3["rows"])),
        "c3_disabled": str(sum(1 for r in c3["rows"] if not r["enabled"])),
        "c4_eps": str(c4["episodes"]), "c4_flagged": str(c4["flagged"]), "c4_months": str(c4["evaluatedMonths"]),
        "c4_rate": "%.3f" % c4["rate"], "c4_classI": str(c4["classI"]),
        "rc_preceded": str(rc["class_i_initiations_preceded_by_an_episode_start"]),
        "rc_initiations": str(rc["class_i_initiations_in_evaluated_span_by_forecast_code"]),
        "rc_episodes_in_window": str(rc["episodes_whose_start_falls_in_the_18_months_before_a_class_i_initiation"]),
        "rc_always": str(rc["always_flag_rule"]["class_i_initiations_preceded"]),
        "rc_events": str(rm["events_in_window"]), "rc_classI_all": str(rm["class_i_events"]),
        "rc_k": nf(rm["records_with_k_numbers"]), "rc_records": nf(rm["in_scope_product_records"]),
        "rc_k_pct": pct(rm["records_with_k_numbers"] / max(1, rm["in_scope_product_records"]), 1),
        "total_eligible": nf(total_eligible), "total_raw": nf(total_raw), "excluded": nf(excluded),
        "sha_local": sha_local[:16] + "..." if sha_local else "see the receipt",
        "prereg_commit": preregistration_commit, "model_commit": model_commit,
        "c5_missing": nf(c5["missingEventDate"]),
        "c1_finding": html.escape(c1["finding"]), "c2_finding": html.escape(c2["finding"]), "c3_finding": html.escape(c3["finding"]),
        "c4_finding": html.escape(c4["finding"]), "c5_finding": html.escape(c5["finding"]),
        "disclaimer": html.escape(DISCLAIMER),
        "c1_card": chart_card("c1", "01", "The outlook", 480, "glacier", c1["annotation"],
                              [("Chart 1 data: %s by month, with the one-month-ahead point and 80%% range" % code,
                                table("tbl-c1", "Chart 1 data: eligible reports per month for %s, the model in use's point and 80%% range (M-01, M-03)" % code,
                                      ["Month", "Reports received", "Point", "80% low", "80% high"], c1["table"]))]),
        "c2_card": chart_card("c2", "02", "The locked test", 460, "madrona", c2["annotation"],
                              [("Chart 2 data: the locked test for %s" % code,
                                table("tbl-c2", "Chart 2 data: locked-test months for %s, actual against both models and the 80%% range (M-03, M-04)" % code,
                                      ["Month", "Actual", "Candidate point", "Trailing mean point", "80% low", "80% high"], c2["table"]))]),
        "c3_card": chart_card("c3", "03", "Did the ranges hold", 330, "evergreen", c3["annotation"],
                              [("Chart 3 data: coverage by code",
                                table("tbl-c3", "Chart 3 data: 80% range coverage in the locked test by code, model in use (M-04)",
                                      ["Code", "Device", "Model in use", "80% coverage", "Months", "Rule enabled"], c3["table"]))]),
        "c4_card": chart_card("c4", "04", "What deserves review", 420, "madrona", c4["annotation"],
                              [("Chart 4 data: flags, episodes and Class I initiations by code",
                                table("tbl-c4", "Chart 4 data: flagged months, episodes and Class I recall initiations by code, 2024-01 to 2026-08 (M-05, M-06)",
                                      ["Code", "Device", "Model in use", "Rule enabled", "Flagged months", "Which", "Episodes", "Class I initiations"], c4["table"]))]),
        "c5_card": chart_card("c5", "05", "How complete is the recent record", 420, "evergreen", c5["annotation"],
                              [("Chart 5 data: %s by event month and receipt lag" % code,
                                table("tbl-c5", "Chart 5 data: %s reports by event month, received within 3, 6 and 12 months (M-02)" % code,
                                      ["Event month", "Reports with this event month", "Within 3 months", "Within 6", "Within 12", "Incomplete at 12"], c5["table"]))]),
        "t_outlook": table("tbl-outlook", "Next-month outlook for every forecast code, model in use, horizon one (M-03)",
                           ["Code", "Device", "Model in use", "Target", "Point", "50% low", "50% high", "80% low", "80% high", "Errors behind the range"], outlook_rows),
        "t_scores": table("tbl-scores", "Scores by code, model and period, horizon one (M-04)",
                          ["Code", "Model", "Period", "Months", "MAE", "MAE / trailing mean", "50% coverage", "80% coverage", "80% width", "WIS"], score_rows),
        "t_queue": table("tbl-queue", "The review queue: every episode under the fixed rule (M-05)",
                         ["Code", "Model in use", "Start", "End", "Months", "Largest excess over point", "Status"], queue_rows),
        "t_work": table("tbl-work", "Workload: evaluated months, flagged months and episodes by code (M-05)",
                        ["Code", "Model in use", "Rule enabled", "Locked 80% coverage", "Evaluated months", "Flagged months", "Episodes", "Episodes per month"], work_rows),
        "t_recall": table("tbl-recall", "Recall events in these codes initiated 2016-01-01 to 2026-08-31, deduplicated on event number (M-06)",
                          ["Initiated", "Codes", "Class", "Classified", "Root cause as recorded", "Product records", "Reason cites reports", "Event"], recall_rows),
        "t_gate": table("tbl-gate", "The cohort gate: 36 complete months and 120 eligible training reports (D2)",
                        ["Code", "Device", "Complete months of 96", "Raw training reports", "Eligible training reports", "Gate"], gate_rows),
        "t_receipt": table("tbl-receipt", "Exclusion receipt: reports removed by the private token list, by code and field (D3)",
                           ["Code", "Field", "Reports"], receipt_rows),
        "data": json.dumps(data, separators=(",", ":")),
        "v_css": asset_v("felix.css"), "v_echarts": asset_v("echarts.min.js"), "v_theme": asset_v("cascadia-echarts-theme.js"),
        "v_page": asset_v("page.js"), "v_favicon": asset_v("favicon.svg"),
        "page_url": PAGE_URL, "site_url": SITE_URL, "case_url": CASE_URL, "repo_url": REPO_URL, "thumb_url": THUMB_URL,
        "as_of": AS_OF, "retrieved": RETRIEVED, "last_updated": LAST_UPDATED,
    }
    out = (DOCS / "template.html").read_text(encoding="utf-8")
    for k, v in f.items():
        out = out.replace("@@%s@@" % k, str(v))
    left = sorted(set(re.findall(r"@@(\w+)@@", out)))
    if left:
        raise SystemExit("unsubstituted tokens in template: %s" % left)
    (DOCS / "index.html").write_text(out, encoding="utf-8", newline="\n")
    print("wrote docs/index.html; headline code %s (%s)" % (code, f["headline_rule"]))
    for c, name in ((c1, "c1"), (c2, "c2"), (c3, "c3"), (c4, "c4"), (c5, "c5")):
        print("  %s: %s" % (name, c["finding"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
