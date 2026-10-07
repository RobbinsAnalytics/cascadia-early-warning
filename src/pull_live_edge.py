"""The live edge: a weekly, watermarked re-read of the count series.

What one run does, in order, and nothing else:

  1. Re-reads the S-02 count series (count=date_received) for the seven
     forecast codes: seven keyless requests, inside the same budget ledger
     src/acquire.py keeps. Every response is saved whole under
     data/live/counts/<vintage>/ with its SHA-256, so each week's view of
     the source is kept as seen (the "vintage"), never overwritten.
  2. Stops, benignly, if the source's own meta.last_updated has not moved
     since the last run: there is nothing new to see.
  3. Re-reads the frozen months (2016-01 to 2026-08) from the new vintage
     and states the variance against the frozen series: late-loaded reports
     make past months read higher; a past month reading materially lower
     is a failed check, because reports do not disappear.
  4. Appends each month beyond the freeze that the source has now loaded
     past (meta.last_updated later than the month's last day), as seen.
  5. Scores every forecast issued for a month seen for the first time:
     the frozen outlook rows, and any forecast this script issued earlier.
  6. Re-issues the next forecasts from the same locked structure
     (config/model.json: the three models, the two horizons, ranges from the
     36 latest elapsed errors) at the newest seen month as origin.
  7. Writes data/live/last_live_run.json and appends
     governance/run_history.jsonl. src/reconcile_live_edge.py turns those
     into health.json, reconciliation.md and the page. This script never
     publishes and never touches data/raw/ or data/conformed/.

WHAT IT DOES NOT DO, STATED SO IT IS NOT ASSUMED. The live months are raw
counts by receipt date with no exclusion applied: the private firm list acts
on report records, and the live edge reads only the count series (the plan
names seven calls a week). The frozen exclusion removed 1 report of 649,083,
and every live figure is labelled "as seen, no exclusion applied". A refresh
of the freeze (src/acquire.py, a deliberate act) is where the exclusion
applies to new months. Live figures are never written into the frozen
tables, and the frozen page's figures are not changed by a run.

Three outcomes a scheduled run can report, by `status`:
  ok                                       the run did its work
  skipped: ...  /  stopped: ...            a benign stop with no failed check
  failed, or any failed check              report it and leave it alone

Usage:
    .venv/Scripts/python.exe src/pull_live_edge.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import sys
import urllib.error
from datetime import datetime, timezone, timedelta

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import acquire  # noqa: E402
from forecast import add_months, golden_baselines, fit_candidate, WINDOW  # noqa: E402
from score import wis as wis_score  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
CONF = REPO / "data" / "conformed"
RAW_COUNTS = REPO / "data" / "raw" / "counts"
CONFIG = REPO / "config" / "model.json"
LIVE = REPO / "data" / "live"
GOV = REPO / "governance"

AS_OF_MONTH = "2026-08"
COHORT = list(acquire.COHORT)
MATERIAL_DOWNWARD = 0.01        # a frozen month reading more than 1% lower than frozen is a failed check

SERIES_FIELDS = ["vintage_utc", "product_code", "month", "reports_as_seen", "last_updated", "basis"]
FORECAST_FIELDS = ["issue_utc", "product_code", "model", "origin", "target", "horizon", "point",
                   "lower50", "upper50", "lower80", "upper80", "calibration_n", "basis"]
SCORE_FIELDS = ["scored_utc", "product_code", "model", "origin", "target", "horizon", "issued_by", "issue_date",
                "point", "lower50", "upper50", "lower80", "upper80", "actual_as_seen", "actual_vintage_utc",
                "error", "abs_error", "covered50", "covered80", "wis"]
BASIS = "raw count by receipt date as seen at the vintage; no exclusion applied"


# ---------------------------------------------------------------------------
# paths, resolved at call time so tests can point them elsewhere
# ---------------------------------------------------------------------------

def paths() -> dict:
    return {
        "vintages": LIVE / "counts",
        "state": LIVE / "watermark.json",
        "last": LIVE / "last_live_run.json",
        "series": LIVE / "live_series.csv",
        "forecasts": LIVE / "live_forecast.csv",
        "scores": LIVE / "live_scores.csv",
        "history": GOV / "run_history.jsonl",
    }


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_csv(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(p: pathlib.Path, rows: list[dict], fields: list[str]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def budget_ok(n: int) -> None:
    """Raises acquire.Budget when the trailing-24h ledger cannot take n more requests."""
    acquire.require_budget(n)


# ---------------------------------------------------------------------------
# pure pieces
# ---------------------------------------------------------------------------

def check_schema(parsed: dict) -> tuple[bool, str]:
    """Every bucket is {time: YYYYMMDD, count: int >= 0}; results is a list."""
    res = parsed.get("results")
    if not isinstance(res, list):
        return False, "results is not a list"
    bad = 0
    for r in res:
        t, c = r.get("time"), r.get("count")
        if not (isinstance(t, str) and len(t) == 8 and t.isdigit()) or not (isinstance(c, int) and c >= 0):
            bad += 1
    return bad == 0, "%d buckets, %d malformed" % (len(res), bad)


def monthly_from_buckets(results: list[dict], first_month: str = "2016-01") -> dict[str, int]:
    out: dict[str, int] = {}
    for r in results:
        m = r["time"][:4] + "-" + r["time"][4:6]
        if m >= first_month:
            out[m] = out.get(m, 0) + int(r["count"])
    return out


def month_end(ym: str) -> str:
    nxt = add_months(ym, 1)
    d = datetime.strptime(nxt + "-01", "%Y-%m-%d") - timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def seen_months(last_updated: str, as_of_month: str = AS_OF_MONTH) -> list[str]:
    """Months after the freeze whose last day is before the source's last_updated."""
    out = []
    m = add_months(as_of_month, 1)
    while month_end(m) < last_updated:
        out.append(m)
        m = add_months(m, 1)
    return out


def frozen_tables() -> tuple[dict, dict, dict, list[dict]]:
    """eligible and raw per code per month; errors per (code, model, h); the outlook rows."""
    eligible: dict[str, dict[str, int]] = {}
    raw: dict[str, dict[str, int]] = {}
    for r in read_csv(CONF / "monthly_report_count.csv"):
        eligible.setdefault(r["product_code"], {})[r["month"]] = int(r["eligible_reports"])
        raw.setdefault(r["product_code"], {})[r["month"]] = int(r["raw_reports"])
    errs: dict[tuple[str, str, int], list[tuple[str, float]]] = {}
    for r in read_csv(CONF / "forecast_scored.csv"):
        if r["error"] == "":
            continue
        errs.setdefault((r["product_code"], r["model"], int(r["horizon"])), []).append((r["target"], float(r["error"])))
    for k in errs:
        errs[k].sort()
    outlook = [r for r in read_csv(CONF / "forecast.csv") if r["period"] == "outlook"]
    return eligible, raw, errs, outlook


def frozen_last_updated() -> str:
    p = RAW_COUNTS / ("%s_date_received.json" % COHORT[0])
    return (json.loads(p.read_text(encoding="utf-8")).get("meta") or {}).get("last_updated", "")


def ranges(err_list: list[tuple[str, float]], point: float, cfg: dict) -> dict:
    q = cfg["intervals"]["levels"]
    min_n = cfg["intervals"]["min_calibration_n"]
    e = [v for _, v in err_list][-WINDOW:]
    row = {"lower50": "", "upper50": "", "lower80": "", "upper80": "", "calibration_n": len(e)}
    if len(e) >= min_n:
        arr = np.asarray(e, dtype=float)
        lo50, hi50 = np.quantile(arr, q["50"])
        lo80, hi80 = np.quantile(arr, q["80"])
        row.update({"lower50": "%.6f" % max(0.0, point + lo50), "upper50": "%.6f" % max(0.0, point + hi50),
                    "lower80": "%.6f" % max(0.0, point + lo80), "upper80": "%.6f" % max(0.0, point + hi80)})
    return row


def reissue(code: str, series: dict[str, int], errs: dict, cfg: dict, origin: str, issue_utc: str) -> tuple[list[dict], int]:
    """The three models at every horizon from `origin`, ranges from the errors elapsed by then."""
    months = sorted(m for m in series if m <= origin)
    history = [series[m] for m in months]
    rows, fits_failed = [], 0
    cand = fit_candidate(history)
    if not cand or "error" in cand:
        fits_failed = 1
    for h in cfg["horizons"]:
        target = add_months(origin, h)
        base = golden_baselines(series, origin, h)
        pts = {"baseline_a": base["baseline_a"], "baseline_b": base["baseline_b"],
               "candidate": (None if fits_failed else max(0.0, math.expm1(cand["log_points"][h - 1])))}
        for model, pt in pts.items():
            row = {"issue_utc": issue_utc, "product_code": code, "model": model, "origin": origin, "target": target,
                   "horizon": h, "point": "" if pt is None else "%.6f" % pt, "basis": BASIS}
            if pt is None:
                row.update({"lower50": "", "upper50": "", "lower80": "", "upper80": "", "calibration_n": 0})
            else:
                elapsed = [(t, e) for t, e in errs.get((code, model, h), []) if t <= origin]
                row.update(ranges(elapsed, pt, cfg))
            rows.append(row)
    return rows, fits_failed


def score_row(fc: dict, actual: int, vintage: str, issued_by: str, scored_utc: str) -> dict:
    pt = float(fc["point"])
    err = actual - pt
    row = {"scored_utc": scored_utc, "product_code": fc["product_code"], "model": fc["model"], "origin": fc["origin"],
           "target": fc["target"], "horizon": fc["horizon"], "issued_by": issued_by,
           "issue_date": fc.get("issue_date") or fc.get("issue_utc", "")[:10],
           "point": fc["point"], "lower50": fc["lower50"], "upper50": fc["upper50"], "lower80": fc["lower80"],
           "upper80": fc["upper80"], "actual_as_seen": actual, "actual_vintage_utc": vintage,
           "error": "%.6f" % err, "abs_error": "%.6f" % abs(err), "covered50": "", "covered80": "", "wis": ""}
    if fc["lower80"] != "":
        lo50, hi50, lo80, hi80 = (float(fc[k]) for k in ("lower50", "upper50", "lower80", "upper80"))
        row["covered50"] = "true" if lo50 <= actual <= hi50 else "false"
        row["covered80"] = "true" if lo80 <= actual <= hi80 else "false"
        row["wis"] = "%.6f" % wis_score(actual, pt, lo50, hi50, lo80, hi80)
    return row


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def load_state(p: pathlib.Path) -> dict:
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"last_updated_seen": None, "runs": 0, "vintages": []}


def run(client_factory=None) -> dict:
    P = paths()
    started = now_utc()
    run_rec = {"started_utc": started, "finished_utc": None, "status": "ok", "passed": None, "checks": [],
               "error": None, "requests_made": 0, "last_updated": None, "vintage": None,
               "months_appended": {}, "forecasts_issued": 0, "forecasts_scored": 0,
               "frozen_variance": None, "notes": []}

    def check(name, value, expectation=None, passed=None):
        if passed is None:
            passed = True if expectation is None else (value == expectation)
        run_rec["checks"].append({"check": name, "value": value, "expected": expectation, "passed": bool(passed)})
        return passed

    state = load_state(P["state"])
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        frozen_lu = frozen_last_updated()
        check("frozen datum (meta.last_updated at the freeze)", frozen_lu, passed=bool(frozen_lu))
        try:
            budget_ok(len(COHORT))
        except acquire.Budget as exc:
            run_rec["status"] = "skipped: no request budget in the trailing 24h"
            run_rec["notes"].append(str(exc))
            return run_rec
        client = (client_factory or acquire.Client)()
        responses: dict[str, tuple[bytes, dict]] = {}
        for code in COHORT:
            url = acquire.count_url(code, "date_received")
            try:
                body, parsed, info = client.get_json(url, label="live S-02 %s" % code)
            except acquire.SourceMoved as exc:
                check("one meta.last_updated across the seven responses", str(exc), passed=False)
                run_rec["status"] = "failed"
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    run_rec["status"] = "stopped: rate limited"
                    run_rec["notes"].append("HTTP 429 twice on %s" % code)
                else:
                    run_rec["status"] = "stopped: upstream failure"
                    run_rec["notes"].append("HTTP %d on %s" % (exc.code, code))
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                run_rec["status"] = "stopped: upstream failure"
                run_rec["notes"].append("%s on %s" % (exc, code))
                break
            check("HTTP status, %s" % code, info.get("status"), 200)
            ok, detail = check_schema(parsed)
            check("response schema, %s" % code, detail, passed=ok)
            responses[code] = (body, parsed)
        run_rec["requests_made"] = getattr(client, "requests_made", len(responses))
        if run_rec["status"] != "ok":
            return run_rec

        lu = getattr(client, "datum", {}).get("event") or (responses[COHORT[0]][1].get("meta") or {}).get("last_updated")
        run_rec["last_updated"] = lu
        check("meta.last_updated present", lu, passed=bool(lu))
        check("meta.last_updated not before the frozen datum", lu, passed=bool(lu) and lu >= frozen_lu)
        if not all(c["passed"] for c in run_rec["checks"]):
            run_rec["status"] = "failed"
            return run_rec
        if lu == state.get("last_updated_seen"):
            run_rec["status"] = "skipped: source unchanged since %s" % lu
            return run_rec

        # the vintage, saved whole
        vintage = started.replace("-", "").replace(":", "")[:15].replace("T", "T")
        vdir = P["vintages"] / vintage
        vdir.mkdir(parents=True, exist_ok=True)
        files = {}
        for code, (body, _) in responses.items():
            f = vdir / ("%s_date_received.json" % code)
            f.write_bytes(body)
            files[f.name] = hashlib.sha256(body).hexdigest()
        (vdir / "manifest.json").write_text(json.dumps({"vintage_utc": started, "last_updated": lu, "sha256": files},
                                                       indent=1) + "\n", encoding="utf-8", newline="\n")
        run_rec["vintage"] = vintage
        check("responses saved as a vintage", len(files), len(COHORT))

        eligible, raw, errs, outlook = frozen_tables()
        live_monthly = {code: monthly_from_buckets(parsed["results"]) for code, (_, parsed) in responses.items()}

        # frozen months, re-read
        compared, higher, lower, added, material = 0, 0, 0, 0, []
        for code in COHORT:
            for m, f in raw.get(code, {}).items():
                l = live_monthly[code].get(m, 0)
                compared += 1
                if l > f:
                    higher += 1
                    added += l - f
                elif l < f:
                    lower += 1
                    if (f - l) > MATERIAL_DOWNWARD * f:
                        material.append({"code": code, "month": m, "frozen": f, "live": l})
        run_rec["frozen_variance"] = {"months_compared": compared, "months_reading_higher": higher,
                                      "reports_added_to_frozen_months": added, "months_reading_lower": lower,
                                      "material_downward": material[:20]}
        check("frozen months re-read", compared, passed=compared > 0)
        check("frozen months reading higher (late loads)", higher)
        check("frozen months rewritten downward by more than %d%%" % int(MATERIAL_DOWNWARD * 100), len(material), 0)

        # months beyond the freeze that the source has loaded past
        months = seen_months(lu)
        check("months elapsed and loaded beyond the freeze", ", ".join(months) or "none")
        series_rows = read_csv(P["series"])
        appended: dict[str, list[str]] = {}
        for code in COHORT:
            for m in months:
                series_rows.append({"vintage_utc": started, "product_code": code, "month": m,
                                    "reports_as_seen": live_monthly[code].get(m, 0), "last_updated": lu, "basis": BASIS})
                appended.setdefault(code, []).append(m)
        if months:
            write_csv(P["series"], series_rows, SERIES_FIELDS)
        run_rec["months_appended"] = appended

        # the latest reading of every live month, by vintage
        latest: dict[tuple[str, str], tuple[str, int]] = {}
        for r in series_rows:
            k = (r["product_code"], r["month"])
            if k not in latest or r["vintage_utc"] > latest[k][0]:
                latest[k] = (r["vintage_utc"], int(r["reports_as_seen"]))

        # score every forecast whose target has now been seen, once, at first sight
        scores = read_csv(P["scores"])
        done = {(r["product_code"], r["model"], r["origin"], r["target"], r["horizon"]) for r in scores}
        live_fc = read_csv(P["forecasts"])
        n_scored = 0
        for fc, issued_by in [(r, "frozen") for r in outlook] + [(r, "live") for r in live_fc]:
            key = (fc["product_code"], fc["model"], fc["origin"], fc["target"], str(fc["horizon"]))
            if key in done or fc["point"] == "" or (fc["product_code"], fc["target"]) not in latest:
                continue
            vint, actual = latest[(fc["product_code"], fc["target"])]
            scores.append(score_row(fc, actual, vint, issued_by, started))
            done.add(key)
            n_scored += 1
        if n_scored:
            write_csv(P["scores"], scores, SCORE_FIELDS)
        run_rec["forecasts_scored"] = n_scored
        check("forecasts scored at first sight of their month", n_scored)

        # re-issue from the newest seen month, once per origin
        for r in scores:
            errs.setdefault((r["product_code"], r["model"], int(r["horizon"])), []).append((r["target"], float(r["error"])))
        for k in errs:
            errs[k].sort()
        issued_origins = {(r["product_code"], r["origin"]) for r in live_fc}
        n_issued, fits_failed = 0, 0
        for code in COHORT:
            seen_here = sorted(m for (c, m) in latest if c == code)
            if not seen_here:
                continue
            origin = seen_here[-1]
            if (code, origin) in issued_origins:
                continue
            series = dict(eligible.get(code, {}))
            series.update({m: v for (c, m), (_, v) in latest.items() if c == code and m <= origin})
            rows, failed = reissue(code, series, errs, cfg, origin, started)
            live_fc.extend(rows)
            n_issued += len(rows)
            fits_failed += failed
        if n_issued:
            write_csv(P["forecasts"], live_fc, FORECAST_FIELDS)
        run_rec["forecasts_issued"] = n_issued
        check("forecasts issued this run", n_issued)
        check("candidate fits that failed", fits_failed, 0)
        state["last_updated_seen"] = lu
        state.setdefault("vintages", []).append(vintage)
    except Exception as exc:  # noqa: BLE001
        run_rec["status"] = "failed"
        run_rec["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        run_rec["finished_utc"] = now_utc()
        failed_checks = [c["check"] for c in run_rec["checks"] if not c["passed"]]
        if failed_checks and run_rec["status"] == "ok":
            run_rec["status"] = "failed"
        run_rec["passed"] = run_rec["status"] != "failed" and not failed_checks and run_rec["error"] is None
        state["runs"] = int(state.get("runs", 0)) + 1
        state["last_run_utc"] = run_rec["finished_utc"]
        P["state"].parent.mkdir(parents=True, exist_ok=True)
        P["state"].write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8", newline="\n")
        P["last"].write_text(json.dumps(run_rec, indent=1) + "\n", encoding="utf-8", newline="\n")
        hist = {k: run_rec[k] for k in ("started_utc", "finished_utc", "status", "passed", "requests_made",
                                        "last_updated", "vintage", "forecasts_issued", "forecasts_scored", "error")}
        hist["checks_total"] = len(run_rec["checks"])
        hist["checks_failed"] = failed_checks
        hist["months_appended"] = sum(len(v) for v in run_rec["months_appended"].values())
        P["history"].parent.mkdir(parents=True, exist_ok=True)
        with P["history"].open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(hist) + "\n")
    return run_rec


def main() -> int:
    r = run()
    failed = [c["check"] for c in r["checks"] if not c["passed"]]
    print("live edge: %s" % r["status"])
    print("  requests %d; last_updated %s; vintage %s" % (r["requests_made"], r["last_updated"], r["vintage"]))
    print("  months appended %d; forecasts scored %d; issued %d"
          % (sum(len(v) for v in r["months_appended"].values()), r["forecasts_scored"], r["forecasts_issued"]))
    if r["frozen_variance"]:
        fv = r["frozen_variance"]
        print("  frozen months re-read %d: %d higher (+%d reports), %d lower, %d material"
              % (fv["months_compared"], fv["months_reading_higher"], fv["reports_added_to_frozen_months"],
                 fv["months_reading_lower"], len(fv["material_downward"])))
    for c in r["checks"]:
        print("  %s  %s: %s" % ("PASS" if c["passed"] else "FAIL", c["check"], c["value"]))
    if r["error"]:
        print("  error: %s" % r["error"])
    if failed:
        print("  checks failed: %s" % ", ".join(failed))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
