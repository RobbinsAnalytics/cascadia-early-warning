"""forecast.py -- PATH 1: rolling-origin forecasts, written before actuals are joined.

Two stages, and the order is enforced by the git log of config/model.json:

    python src/forecast.py --stage development
        origins 2018-12 to 2023-11: warmup targets (calibration only),
        development targets (scored, selection), and the handful of horizon-3
        targets that fall in 2024-01 and 2024-02 from origins before 2023-12
        (labelled 'unscored'; they belong to neither period).
    python src/forecast.py --stage locked
        origins 2023-12 to 2026-08: locked, recent and outlook targets.
        Refuses to run unless config/model.json carries 'promoted' for every
        forecast code, which score.py --promote writes from development scores.

Three models per origin (D6), ranges from the empirical quantiles of each
model's own past errors (D7). Every row's origin precedes its target. Actuals
are never read here except as the history the models are fitted on and the
errors that calibrate the ranges, both strictly at or before the origin.

Writes data/conformed/forecast.csv and data/conformed/forecast_states.csv.
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import sys
import warnings
from datetime import date

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_model import read_csv, write_csv  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
CONF = REPO / "data" / "conformed"
CONFIG = REPO / "config" / "model.json"
OUT = CONF / "forecast.csv"
STATES = CONF / "forecast_states.csv"

WINDOW = 36            # errors behind each range (D7)
FIRST_ORIGIN = "2018-12"
LAST_ORIGIN = "2026-08"
MODELS = ("baseline_a", "baseline_b", "candidate")
ISSUE_DATE_ACTUAL = "2026-10-06"


# ---------------------------------------------------------------------------
# month arithmetic
# ---------------------------------------------------------------------------

def add_months(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    n = y * 12 + (m - 1) + k
    return "%04d-%02d" % (n // 12, n % 12 + 1)


def months_between(a: str, b: str) -> int:
    return (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7]))


# ---------------------------------------------------------------------------
# golden API (Path 1)
# ---------------------------------------------------------------------------

def golden_baselines(series: dict[str, int], origin: str, horizon: int) -> dict:
    """Baseline A: trailing three-month mean at the origin. Baseline B: the value
    twelve months before the target. None where history is too short."""
    out = {"baseline_a": None, "baseline_b": None}
    last3 = [series.get(add_months(origin, -k)) for k in (0, 1, 2)]
    if all(v is not None for v in last3):
        out["baseline_a"] = sum(last3) / 3.0
    target = add_months(origin, horizon)
    prior = series.get(add_months(target, -12))
    if prior is not None:
        out["baseline_b"] = float(prior)
    return out


def golden_ets_point(level: float, trend: float, phi: float, seasonals: list[float], h: int) -> float:
    """h-step point of ETS(A,Ad,A) from final states, seasonals oldest first for
    months T-11..T: level + trend * sum(phi^j, j=1..h) + s[(h-1) mod 12]."""
    damp = sum(phi ** j for j in range(1, h + 1))
    return level + trend * damp + seasonals[(h - 1) % 12]


# ---------------------------------------------------------------------------
# the candidate
# ---------------------------------------------------------------------------

def fit_candidate(history: list[int]) -> dict | None:
    """Fit ETS(A,Ad,A) on log1p(history); return exported states or None."""
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel
    y = np.log1p(np.asarray(history, dtype=float))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            model = ETSModel(y, error="add", trend="add", damped_trend=True,
                             seasonal="add", seasonal_periods=12)
            res = model.fit(disp=False, maxiter=500)
        except Exception as exc:  # noqa: BLE001
            return {"error": "%s: %s" % (type(exc).__name__, exc)}
    p = res.params
    names = list(model.param_names)
    prm = {n: float(v) for n, v in zip(names, p)}
    states = {
        "smoothing_level": prm.get("smoothing_level"),
        "smoothing_trend": prm.get("smoothing_trend"),
        "smoothing_seasonal": prm.get("smoothing_seasonal"),
        "damping_trend": prm.get("damping_trend"),
        "level": float(res.level[-1]),
        "trend": float(res.trend[-1]),
        "seasonals": [float(v) for v in res.season[-12:]],
        "aic": float(res.aic),
        "log_likelihood": float(res.llf),
        "n_obs": len(history),
    }
    # The library's own forecast, and the recurrence from the exported states,
    # must agree; otherwise the export is wrong and the independent path would
    # be checking the wrong thing.
    lib = res.forecast(3)
    for h in (1, 2, 3):
        rec = golden_ets_point(states["level"], states["trend"], states["damping_trend"], states["seasonals"], h)
        if abs(rec - float(lib[h - 1])) > 1e-6 * max(1.0, abs(rec)):
            states["export_mismatch"] = "h=%d library %.9f recurrence %.9f" % (h, lib[h - 1], rec)
            break
    states["log_points"] = [float(v) for v in lib]
    return states


# ---------------------------------------------------------------------------
# periods
# ---------------------------------------------------------------------------

def period_of(cfg: dict, origin: str, target: str) -> str:
    P = cfg["periods"]
    if target > "2026-08":
        return "outlook"
    if P["recent"]["targets"][0] <= target <= P["recent"]["targets"][1]:
        return "recent" if origin >= P["recent"]["min_origin"] else "unscored"
    if P["locked"]["targets"][0] <= target <= P["locked"]["targets"][1]:
        return "locked" if origin >= P["locked"]["min_origin"] else "unscored"
    if P["development"]["targets"][0] <= target <= P["development"]["targets"][1]:
        return "development"
    if P["warmup"]["targets"][0] <= target <= P["warmup"]["targets"][1]:
        return "warmup"
    return "unscored"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if "--stage" not in argv:
        sys.exit("usage: forecast.py --stage development|locked")
    stage = argv[argv.index("--stage") + 1]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    gate = read_csv(CONF / "cohort_gate.csv")
    codes = [g["product_code"] for g in gate if g["forecast"] == "true"]
    if stage == "locked":
        promoted = cfg.get("promoted") or {}
        missing = [c for c in codes if c not in promoted]
        if missing:
            sys.exit("config/model.json carries no promotion decision for %s; run score.py --promote "
                     "on the development period first, and commit it" % missing)
        origins = [add_months("2023-12", k) for k in range(0, months_between("2023-12", LAST_ORIGIN) + 1)]
    elif stage == "development":
        origins = [add_months(FIRST_ORIGIN, k) for k in range(0, months_between(FIRST_ORIGIN, "2023-11") + 1)]
    else:
        sys.exit("unknown stage %s" % stage)

    m01 = read_csv(CONF / "monthly_report_count.csv")
    series = {c: {} for c in codes}
    for r in m01:
        if r["product_code"] in series:
            series[r["product_code"]][r["month"]] = int(r["eligible_reports"])
    horizons = cfg["horizons"]
    q = cfg["intervals"]["levels"]
    min_n = cfg["intervals"]["min_calibration_n"]

    existing = read_csv(OUT) if OUT.exists() else []
    existing_states = read_csv(STATES) if STATES.exists() else []
    if stage == "development":
        existing = [r for r in existing if r["origin"] >= "2023-12"]
        existing_states = [r for r in existing_states if r["origin"] >= "2023-12"]
    else:
        if any(r["origin"] >= "2023-12" for r in existing):
            sys.exit("locked-period rows already exist in forecast.csv; the locked test runs once")
        existing_states = [r for r in existing_states if r["origin"] < "2023-12"]

    rows, state_rows = [], []
    for code in codes:
        s = series[code]
        all_months = sorted(s)
        # errors known so far, per (model, horizon): list of (target, error)
        errs: dict[tuple[str, int], list[tuple[str, float]]] = {}
        # every origin from the first one, so that the error history at a locked
        # origin is the same whichever stage wrote it: recompute points from the
        # start, write only this stage's origins.
        first = FIRST_ORIGIN
        span = [add_months(first, k) for k in range(0, months_between(first, origins[-1]) + 1)]
        for origin in span:
            history = [s[m] for m in all_months if m <= origin]
            pts: dict[tuple[str, int], float | None] = {}
            base = golden_baselines(s, origin, 1)
            for h in horizons:
                b = golden_baselines(s, origin, h)
                pts[("baseline_a", h)] = base["baseline_a"]
                pts[("baseline_b", h)] = b["baseline_b"]
            cand = fit_candidate(history) if origin in origins else None
            if origin in origins:
                if cand and "error" not in cand:
                    for h in horizons:
                        pts[("candidate", h)] = max(0.0, math.expm1(cand["log_points"][h - 1]))
                else:
                    for h in horizons:
                        pts[("candidate", h)] = None
            else:
                # Not this stage's origin: the candidate's errors for earlier
                # targets come from the rows the earlier stage wrote.
                for h in horizons:
                    pts[("candidate", h)] = None
            # harvest errors for targets elapsed at this origin from earlier rows
            for (model, h), pt in pts.items():
                target = add_months(origin, h)
                if pt is None:
                    continue
                if target <= LAST_ORIGIN and target in s:
                    errs.setdefault((model, h), []).append((target, s[target] - pt))
            if origin not in origins:
                continue
            # calibration: errors of targets <= origin, latest WINDOW
            for (model, h), pt in pts.items():
                target = add_months(origin, h)
                period = period_of(cfg, origin, target)
                row = {"product_code": code, "model": model, "origin": origin, "target": target,
                       "horizon": h, "issue_date": (ISSUE_DATE_ACTUAL if period == "outlook"
                                                    else add_months(origin, 1) + "-01"),
                       "period": period, "point": "" if pt is None else "%.6f" % pt,
                       "lower50": "", "upper50": "", "lower80": "", "upper80": "", "calibration_n": 0}
                e = [er for (t, er) in errs.get((model, h), []) if t <= origin]
                e = e[-WINDOW:]
                row["calibration_n"] = len(e)
                if pt is not None and len(e) >= min_n:
                    arr = np.asarray(e, dtype=float)
                    lo50, hi50 = np.quantile(arr, q["50"])
                    lo80, hi80 = np.quantile(arr, q["80"])
                    row["lower50"] = "%.6f" % max(0.0, pt + lo50)
                    row["upper50"] = "%.6f" % max(0.0, pt + hi50)
                    row["lower80"] = "%.6f" % max(0.0, pt + lo80)
                    row["upper80"] = "%.6f" % max(0.0, pt + hi80)
                rows.append(row)
            st = {"product_code": code, "origin": origin, "n_obs": len(history)}
            if cand and "error" not in cand:
                st.update({k: ("%.9f" % v if isinstance(v, float) else v) for k, v in cand.items()
                           if k in ("smoothing_level", "smoothing_trend", "smoothing_seasonal",
                                    "damping_trend", "level", "trend", "aic", "log_likelihood")})
                for i, v in enumerate(cand["seasonals"], 1):
                    st["s%d" % i] = "%.9f" % v
                st["export_mismatch"] = cand.get("export_mismatch", "")
                st["fit_error"] = ""
            else:
                st["fit_error"] = (cand or {}).get("error", "not fitted")
            state_rows.append(st)
        print("  %s: %d origins, %d rows" % (code, len(origins), len(origins) * len(MODELS) * len(horizons)))

    all_rows = existing + rows
    all_rows.sort(key=lambda r: (r["product_code"], r["origin"], r["horizon"], r["model"]))
    write_csv(OUT, all_rows)
    cols = ["product_code", "origin", "n_obs", "smoothing_level", "smoothing_trend", "smoothing_seasonal",
            "damping_trend", "level", "trend"] + ["s%d" % i for i in range(1, 13)] + \
           ["aic", "log_likelihood", "export_mismatch", "fit_error"]
    norm_states = [{c: r.get(c, "") for c in cols} for r in existing_states + state_rows]
    norm_states.sort(key=lambda r: (r["product_code"], r["origin"]))
    write_csv(STATES, norm_states)
    mism = [r for r in state_rows if r.get("export_mismatch")]
    fails = [r for r in state_rows if r.get("fit_error")]
    print("wrote %d forecast rows (%d this stage); %d state rows; %d export mismatches; %d fit failures"
          % (len(all_rows), len(rows), len(norm_states), len(mism), len(fails)))
    for r in fails[:10]:
        print("    fit failure %s %s: %s" % (r["product_code"], r["origin"], r["fit_error"]))
    return 1 if mism else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
