"""Reconcile the live edge against the frozen snapshot, and surface it.

Reads what src/pull_live_edge.py wrote (data/live/, governance/run_history.jsonl)
and the frozen tables, and writes:

    governance/health.json          the machine-readable record a page renders:
                                    the frozen baseline, what the live edge has
                                    seen, the last run and its checks, the last
                                    successful run and the last run that was not ok
    governance/reconciliation.md    the human record: the frozen series re-read,
                                    the months appended as seen, the forecasts
                                    scored as their months elapsed, the latest
                                    live outlook, and why the two views differ
    docs/index.html                 rebuilt, as the last step, so the page's
                                    live-edge line matches the record. Rebuilding
                                    writes the file and stops; nothing is published.

IT DOES NOT TRY TO MAKE THE NUMBERS MATCH. A frozen month reading higher in a
later vintage is a late-loaded report, which is what the lag chart on the page
is about; the reconciliation names the size of it. A live month is a raw count
with no exclusion applied, and says so.

Usage:
    .venv/Scripts/python.exe src/reconcile_live_edge.py
"""
from __future__ import annotations

import csv
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

REPO = pathlib.Path(__file__).resolve().parent.parent
CONF = REPO / "data" / "conformed"
LIVE = REPO / "data" / "live"
GOV = REPO / "governance"
AS_OF = "2026-08-31"
RETRIEVED = "2026-10-06"


def read_csv(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def nf(x) -> str:
    return "{:,}".format(int(round(float(x))))


def main() -> int:
    last_p = LIVE / "last_live_run.json"
    hist_p = GOV / "run_history.jsonl"
    if not last_p.exists():
        print("no live run on record (data/live/last_live_run.json missing); run src/pull_live_edge.py first")
        return 1
    run = json.loads(last_p.read_text(encoding="utf-8"))
    history = [json.loads(l) for l in hist_p.read_text(encoding="utf-8").splitlines() if l.strip()] if hist_p.exists() else []

    def latest(pred):
        for r in reversed(history):
            if pred(r):
                return r
        return None

    last_ok = latest(lambda r: r.get("status") == "ok")
    last_not_ok = latest(lambda r: r.get("status") != "ok")
    last_failure = latest(lambda r: r.get("status") == "failed" or r.get("checks_failed"))

    # frozen baseline
    m01 = read_csv(CONF / "monthly_report_count.csv")
    codes = sorted({r["product_code"] for r in m01})
    eligible_total = sum(int(r["eligible_reports"]) for r in m01)
    raw = {(r["product_code"], r["month"]): int(r["raw_reports"]) for r in m01}
    outlook = [r for r in read_csv(CONF / "forecast.csv") if r["period"] == "outlook"]
    frozen_lu = (json.loads((REPO / "data" / "raw" / "counts" / "DSQ_date_received.json").read_text(encoding="utf-8"))
                 .get("meta") or {}).get("last_updated")

    # live edge
    series = read_csv(LIVE / "live_series.csv")
    scores = read_csv(LIVE / "live_scores.csv")
    live_fc = read_csv(LIVE / "live_forecast.csv")
    state = json.loads((LIVE / "watermark.json").read_text(encoding="utf-8")) if (LIVE / "watermark.json").exists() else {}
    latest_reading: dict[tuple[str, str], tuple[str, int]] = {}
    for r in series:
        k = (r["product_code"], r["month"])
        if k not in latest_reading or r["vintage_utc"] > latest_reading[k][0]:
            latest_reading[k] = (r["vintage_utc"], int(r["reports_as_seen"]))
    months_seen = sorted({m for (_, m) in latest_reading})
    in_use = {c: v["model_in_use"] for c, v in json.loads((REPO / "config" / "model.json").read_text(encoding="utf-8")).get("promoted", {}).items()}
    scored_in_use = [r for r in scores if r["model"] == in_use.get(r["product_code"]) and r["horizon"] == "1"]
    cov80 = [r["covered80"] == "true" for r in scored_in_use if r["covered80"] != ""]
    mae = (sum(float(r["abs_error"]) for r in scored_in_use) / len(scored_in_use)) if scored_in_use else None
    live_origins = sorted({r["origin"] for r in live_fc})
    latest_origin = live_origins[-1] if live_origins else None
    latest_outlook = [r for r in live_fc if r["origin"] == latest_origin and r["model"] == in_use.get(r["product_code"]) and r["horizon"] == "1"] if latest_origin else []

    fv = run.get("frozen_variance") or {}
    health = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "module": "cascadia-early-warning",
        "frozen_baseline": {
            "as_of": AS_OF, "retrieved": RETRIEVED, "source_last_updated": frozen_lu,
            "codes": codes, "eligible_reports": eligible_total,
            "outlook_origin": max(r["origin"] for r in outlook) if outlook else None,
        },
        "live_edge": {
            "source_last_updated_seen": state.get("last_updated_seen"),
            "runs_total": state.get("runs", 0),
            "vintages": state.get("vintages", []),
            "months_seen_beyond_freeze": months_seen,
            "readings_recorded": len(series),
            "basis": "raw count by receipt date as seen at the vintage; no exclusion applied",
            "frozen_months_re_read": fv.get("months_compared"),
            "frozen_months_reading_higher": fv.get("months_reading_higher"),
            "reports_added_to_frozen_months": fv.get("reports_added_to_frozen_months"),
            "frozen_months_reading_lower": fv.get("months_reading_lower"),
            "forecasts_issued_total": len(live_fc),
            "latest_live_origin": latest_origin,
            "forecasts_scored_total": len(scores),
            "model_in_use_h1_scored": len(scored_in_use),
            "model_in_use_h1_mae": None if mae is None else round(mae, 3),
            "model_in_use_h1_coverage80": None if not cov80 else round(sum(cov80) / len(cov80), 4),
        },
        "last_run": {
            "started_utc": run["started_utc"], "finished_utc": run["finished_utc"], "status": run["status"],
            "passed": run["passed"], "checks_total": len(run["checks"]),
            "checks_failed": [c["check"] for c in run["checks"] if not c["passed"]],
            "error": run.get("error"), "requests_made": run.get("requests_made"),
            "notes": run.get("notes", []),
        },
        "run_history": {
            "runs_recorded": len(history),
            "history_started": history[0]["started_utc"] if history else None,
            "last_successful_run": last_ok,
            "last_run_not_ok": last_not_ok,
            "last_failure": last_failure,
        },
    }
    (GOV / "health.json").write_text(json.dumps(health, indent=1) + "\n", encoding="utf-8", newline="\n")

    # the human record
    L = []
    a = L.append
    a("# Live edge against the frozen snapshot")
    a("")
    a("*Generated by `src/reconcile_live_edge.py`. Regenerate it; never hand-edit it. Machine-readable form: `governance/health.json`.*")
    a("")
    a("| | |")
    a("|---|---|")
    a("| Frozen snapshot | receipts through **%s**, retrieved %s, source last_updated %s |" % (AS_OF, RETRIEVED, frozen_lu))
    a("| Live edge, source last_updated seen | **%s** |" % (state.get("last_updated_seen") or "none yet"))
    a("| Runs recorded | %d (%d with status ok) |" % (len(history), sum(1 for r in history if r.get("status") == "ok")))
    a("| Last run | **%s**, started %s, %d checks, %d failed |" % (run["status"], run["started_utc"], len(run["checks"]),
                                                                  len([c for c in run["checks"] if not c["passed"]])))
    a("| Months seen beyond the freeze | %s |" % (", ".join(months_seen) or "none: the source has not loaded past 2026-08-31"))
    a("")
    a("## What a run is allowed to change")
    a("")
    a("Nothing under `data/raw/` or `data/conformed/`, and no figure on the frozen page. A run writes `data/live/`, "
      "this file, `governance/health.json`, `governance/run_history.jsonl` and rebuilds `docs/index.html` so the "
      "page's one live-edge line matches the record. Live months are raw counts by receipt date as seen at the "
      "vintage, with no exclusion applied; the frozen exclusion removed 1 report of 649,083, and the next freeze "
      "is where the private list acts on new months.")
    a("")
    a("## The frozen months, re-read")
    a("")
    if fv:
        a("The last run re-read every frozen month (2016-01 to 2026-08) for the seven codes from the new vintage.")
        a("")
        a("| | |")
        a("|---|---:|")
        a("| Code-months compared | %s |" % nf(fv.get("months_compared", 0)))
        a("| Reading higher than frozen (late-loaded reports) | %s |" % nf(fv.get("months_reading_higher", 0)))
        a("| Reports added to frozen months, in total | %s |" % nf(fv.get("reports_added_to_frozen_months", 0)))
        a("| Reading lower than frozen | %s |" % nf(fv.get("months_reading_lower", 0)))
        a("| Lower by more than 1%% (a failed check) | %s |" % nf(len(fv.get("material_downward", []))))
        a("")
        a("**It does not balance, and it is not supposed to.** A report is counted by the day FDA received it, and "
          "the source keeps loading reports for weeks after that day, so a month read later reads higher. That is "
          "the lag chart 5 draws. A month reading *lower* would mean the source removed reports from its past; "
          "a material case fails the run and is reported, never absorbed.")
    else:
        a("The last run did not reach the re-read (status: %s)." % run["status"])
    a("")
    a("## Months appended, as seen")
    a("")
    if months_seen:
        a("| Code | " + " | ".join(months_seen) + " |")
        a("|---|" + "---:|" * len(months_seen))
        for c in codes:
            a("| %s | " % c + " | ".join(nf(latest_reading[(c, m)][1]) if (c, m) in latest_reading else "" for m in months_seen) + " |")
        a("")
        a("Each cell is the latest vintage's reading; earlier readings of the same month stay in `data/live/live_series.csv`.")
    else:
        a("None. The source's last_updated (%s) is not past the end of September 2026, so no month beyond the freeze "
          "has been loaded; the frozen outlook for 2026-09 stands unscored." % (state.get("last_updated_seen") or frozen_lu))
    a("")
    a("## Forecasts scored as their months elapsed")
    a("")
    if scored_in_use:
        a("| Code | Model in use | Origin | Target | Point | 80%% range | Actual as seen | Error | Inside 80%% |")
        a("|---|---|---|---|---:|---|---:|---:|---|")
        for r in sorted(scored_in_use, key=lambda r: (r["target"], r["product_code"])):
            a("| %s | %s | %s | %s | %s | %s to %s | %s | %s | %s |" % (
                r["product_code"], r["model"], r["origin"], r["target"], nf(r["point"]),
                nf(r["lower80"]) if r["lower80"] else "", nf(r["upper80"]) if r["upper80"] else "",
                nf(r["actual_as_seen"]), nf(r["error"]), r["covered80"] or "no range"))
        a("")
        a("Model in use, horizon one: %d scored, mean absolute error %s, 80%% coverage %s. Scores are taken once, at the "
          "first vintage that shows the month, and are not revised as the month fills."
          % (len(scored_in_use), nf(mae), ("%.0f%%" % (100 * sum(cov80) / len(cov80))) if cov80 else "n/a"))
    else:
        a("None yet: no forecast's target month has been seen.")
    a("")
    a("## The latest live outlook")
    a("")
    if latest_outlook:
        a("Issued from origin %s by the same locked structure (`config/model.json`), ranges from the 36 latest elapsed errors." % latest_origin)
        a("")
        a("| Code | Model in use | Target | Point | 50%% range | 80%% range | Errors behind the range |")
        a("|---|---|---|---:|---|---|---:|")
        for r in sorted(latest_outlook, key=lambda r: r["product_code"]):
            a("| %s | %s | %s | %s | %s to %s | %s to %s | %s |" % (
                r["product_code"], r["model"], r["target"], nf(r["point"]) if r["point"] else "",
                nf(r["lower50"]) if r["lower50"] else "", nf(r["upper50"]) if r["upper50"] else "",
                nf(r["lower80"]) if r["lower80"] else "", nf(r["upper80"]) if r["upper80"] else "", r["calibration_n"]))
    else:
        a("None issued: the frozen outlook (origin %s) is still the latest." % (max(r["origin"] for r in outlook) if outlook else "n/a"))
    a("")
    a("## Last run, check by check")
    a("")
    a("| Check | Value | Expected | Result |")
    a("|---|---|---|---|")
    for c in run["checks"]:
        a("| %s | %s | %s | %s |" % (c["check"], str(c["value"]).replace("|", "/"), "" if c["expected"] is None else c["expected"],
                                     "PASS" if c["passed"] else "**FAIL**"))
    if run.get("notes"):
        a("")
        a("Notes: " + "; ".join(run["notes"]))
    if run.get("error"):
        a("")
        a("Error: `%s`" % run["error"])
    a("")
    (GOV / "reconciliation.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("wrote governance/health.json and governance/reconciliation.md (last run: %s; %d checks, %d failed)"
          % (run["status"], len(run["checks"]), len(health["last_run"]["checks_failed"])))

    # the page, last, so the health surface is level with the record
    res = subprocess.run([sys.executable, str(REPO / "src" / "build_page.py")], cwd=str(REPO), capture_output=True, text=True)
    if res.returncode != 0:
        print("PAGE REBUILD FAILED; docs/index.html is stale against governance/health.json")
        print(res.stdout[-2000:])
        print(res.stderr[-2000:])
        return 2
    print("rebuilt docs/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
