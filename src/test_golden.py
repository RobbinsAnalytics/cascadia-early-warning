"""test_golden.py -- the hand-specified acceptance fixtures, run on both paths.

Written 2026-10-06 BEFORE any engine code existed, and committed failing. The
expected values in tests/golden/*.csv were computed by hand from the decision
record (D6 to D9) and the metric register; this script only compares.

Each path exposes the same five callables, and neither imports the other:

    Path 1, the engine                 Path 2, the independent re-derivation
    forecast.golden_baselines          validate_measures.golden_baselines
    forecast.golden_ets_point          validate_measures.golden_ets_point
    review.golden_episodes             validate_measures.golden_episodes
    build_model.golden_lag_matched     validate_measures.golden_lag_matched
    score.golden_scores                validate_measures.golden_scores

Signatures:
    golden_baselines(series: dict[str, int], origin: str, horizon: int)
        -> dict with keys "baseline_a", "baseline_b"; a value of None means
           no forecast can be issued (history too short)
    golden_ets_point(level, trend, phi, seasonals_oldest_first: list[float], h)
        -> float, the h-step point in the fitted (log1p) space
    golden_episodes(rows: list[dict(target, actual, point, upper80)])
        -> list of (episode_start, episode_end, months_in_episode)
    golden_lag_matched(reports: list[dict(mdr_report_key, date_of_event, date_received)])
        -> dict event_month -> dict(reports_with_event_month, within_3,
           within_6, within_12, negative_lag); plus key "_missing_event_date"
    golden_scores(rows: list[dict(actual, point, lower50, upper50, lower80, upper80)])
        -> dict(n, mae, coverage50, coverage80, width50, width80, wis)

A path that cannot be imported is a failure, not a skip: that is what
"committed failing" means. Exit 0 only if every expected cell matches on BOTH
paths.

    python src/test_golden.py
"""
from __future__ import annotations

import csv
import importlib
import math
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden"
TOL = 1e-6

PATHS = {
    "Path 1 (engine)": {
        "baselines": ("forecast", "golden_baselines"),
        "ets": ("forecast", "golden_ets_point"),
        "episodes": ("review", "golden_episodes"),
        "lag": ("build_model", "golden_lag_matched"),
        "scores": ("score", "golden_scores"),
    },
    "Path 2 (validate_measures)": {
        "baselines": ("validate_measures", "golden_baselines"),
        "ets": ("validate_measures", "golden_ets_point"),
        "episodes": ("validate_measures", "golden_episodes"),
        "lag": ("validate_measures", "golden_lag_matched"),
        "scores": ("validate_measures", "golden_scores"),
    },
}


def read_csv(name: str) -> list[dict]:
    with open(GOLDEN / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def close(expected: str, actual, label: str, failures: list[str]) -> None:
    if actual is None:
        failures.append("%s: expected %s, got None" % (label, expected))
        return
    try:
        e = float(expected)
        a = float(actual)
    except (TypeError, ValueError):
        if str(expected) != str(actual):
            failures.append("%s: expected %r, got %r" % (label, expected, actual))
        return
    if math.isnan(a) or abs(e - a) > TOL * max(1.0, abs(e)):
        failures.append("%s: expected %s, got %s" % (label, expected, actual))


def load(path_spec: dict) -> tuple[dict, list[str]]:
    sys.path.insert(0, str(REPO / "src"))
    fns, failures = {}, []
    for key, (module_name, fn_name) in path_spec.items():
        try:
            mod = importlib.import_module(module_name)
            fns[key] = getattr(mod, fn_name)
        except Exception as exc:  # noqa: BLE001 -- a missing engine is a failure
            failures.append("cannot load %s.%s: %s: %s" % (module_name, fn_name, type(exc).__name__, exc))
    return fns, failures


def run_path(name: str, spec: dict) -> list[str]:
    fns, failures = load(spec)
    if failures:
        return failures

    # -- baselines ----------------------------------------------------------
    series = {r["month"]: int(r["count"]) for r in read_csv("golden_series.csv")}
    for exp in read_csv("golden_expected_baselines.csv"):
        try:
            out = fns["baselines"](series, exp["origin"], int(exp["horizon"]))
        except Exception as exc:  # noqa: BLE001
            failures.append("%s: baselines raised %s: %s" % (exp["case"], type(exc).__name__, exc))
            continue
        got = out.get(exp["model"])
        if exp["expect_absent"] == "1":
            if got is not None:
                failures.append("%s: expected no %s forecast, got %s" % (exp["case"], exp["model"], got))
        else:
            close(exp["expected_point"], got, "%s %s" % (exp["case"], exp["model"]), failures)

    # -- ETS recurrence -----------------------------------------------------
    st = read_csv("golden_ets_states.csv")[0]
    seasonals = [float(st["s%d" % i]) for i in range(1, 13)]
    for exp in read_csv("golden_expected_ets.csv"):
        try:
            got = fns["ets"](float(st["level"]), float(st["trend"]), float(st["phi"]),
                             seasonals, int(exp["horizon"]))
        except Exception as exc:  # noqa: BLE001
            failures.append("%s: ets raised %s: %s" % (exp["case"], type(exc).__name__, exc))
            continue
        close(exp["expected_log_point"], got, "%s h=%s" % (exp["case"], exp["horizon"]), failures)

    # -- review episodes ----------------------------------------------------
    rows = [{"target": r["target"], "actual": float(r["actual"]), "point": float(r["point"]),
             "upper80": float(r["upper80"])} for r in read_csv("golden_review_input.csv")]
    try:
        eps = fns["episodes"](rows)
        got = [(e[0], e[1], int(e[2])) for e in eps]
    except Exception as exc:  # noqa: BLE001
        failures.append("review: episodes raised %s: %s" % (type(exc).__name__, exc))
        got = None
    if got is not None:
        want = [(r["episode_start"], r["episode_end"], int(r["months_in_episode"]))
                for r in read_csv("golden_expected_review.csv")]
        if got != want:
            failures.append("review: expected episodes %s, got %s" % (want, got))

    # -- lag-matched --------------------------------------------------------
    reports = read_csv("golden_lag_reports.csv")
    try:
        lag = fns["lag"](reports)
    except Exception as exc:  # noqa: BLE001
        failures.append("lag: raised %s: %s" % (type(exc).__name__, exc))
        lag = None
    if lag is not None:
        for exp in read_csv("golden_expected_lag.csv"):
            got = lag.get(exp["event_month"])
            if got is None:
                failures.append("%s: event month %s missing" % (exp["case"], exp["event_month"]))
                continue
            for col in ("reports_with_event_month", "within_3", "within_6", "within_12", "negative_lag"):
                close(exp[col], got.get(col), "%s %s" % (exp["case"], col), failures)
        close("1", lag.get("_missing_event_date"), "lag missing_event_date", failures)

    # -- scores -------------------------------------------------------------
    srows = [{k: float(r[k]) for k in ("actual", "point", "lower50", "upper50", "lower80", "upper80")}
             for r in read_csv("golden_score_input.csv")]
    try:
        sc = fns["scores"](srows)
    except Exception as exc:  # noqa: BLE001
        failures.append("scores: raised %s: %s" % (type(exc).__name__, exc))
        sc = None
    if sc is not None:
        for exp in read_csv("golden_expected_scores.csv"):
            for col in ("n", "mae", "coverage50", "coverage80", "width50", "width80", "wis"):
                close(exp[col], sc.get(col), "%s %s" % (exp["case"], col), failures)
    return failures


def main() -> int:
    n_expected = sum(len(read_csv(f)) for f in (
        "golden_expected_baselines.csv", "golden_expected_ets.csv", "golden_expected_review.csv",
        "golden_expected_lag.csv", "golden_expected_scores.csv"))
    print("Golden fixtures: %d expected rows across five fixtures" % n_expected)
    all_ok = True
    for name, spec in PATHS.items():
        failures = run_path(name, spec)
        if failures:
            all_ok = False
            print("  FAIL  %s: %d mismatch(es)" % (name, len(failures)))
            for f in failures[:40]:
                print("        - " + f)
        else:
            print("  PASS  %s: every expected row matches" % name)
    print("\nGOLDEN: " + ("PASSED" if all_ok else "FAILED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
