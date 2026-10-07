"""score.py -- PATH 1: join actuals to the forecasts and score them (M-04).

    python src/score.py             score every scored period present
    python src/score.py --promote   also write the promotion decision (D8) into
                                    config/model.json from DEVELOPMENT scores
                                    only; refuses if 'promoted' is already set

Writes
    data/conformed/forecast_scored.csv   every scored row with its actual, error,
                                         coverage flags and interval score
    data/conformed/forecast_score.csv    M-04 by code, model, horizon, period

WIS (Bracher et al.): with K central intervals, WIS = (0.5*|y-m| + sum_k (alpha_k/2) * IS_alpha_k) / (K + 0.5),
where IS_alpha = (u - l) + (2/alpha)(l - y) if y < l, + (2/alpha)(y - u) if y > u. Here K = 2, alpha = 0.5 and 0.2.
Coverage is inclusive at the bound.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_model import read_csv, write_csv  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
CONF = REPO / "data" / "conformed"
CONFIG = REPO / "config" / "model.json"
SCORED_PERIODS = ("development", "locked", "recent")


def interval_score(y: float, lo: float, hi: float, alpha: float) -> float:
    s = hi - lo
    if y < lo:
        s += (2.0 / alpha) * (lo - y)
    if y > hi:
        s += (2.0 / alpha) * (y - hi)
    return s


def wis(y: float, point: float, lo50: float, hi50: float, lo80: float, hi80: float) -> float:
    k = 2
    return (0.5 * abs(y - point) + (0.5 / 2) * interval_score(y, lo50, hi50, 0.5)
            + (0.2 / 2) * interval_score(y, lo80, hi80, 0.2)) / (k + 0.5)


def golden_scores(rows: list[dict]) -> dict:
    """rows: actual, point, lower50, upper50, lower80, upper80 (floats)."""
    n = len(rows)
    mae = sum(abs(r["actual"] - r["point"]) for r in rows) / n
    c50 = sum(1 for r in rows if r["lower50"] <= r["actual"] <= r["upper50"]) / n
    c80 = sum(1 for r in rows if r["lower80"] <= r["actual"] <= r["upper80"]) / n
    w50 = sum(r["upper50"] - r["lower50"] for r in rows) / n
    w80 = sum(r["upper80"] - r["lower80"] for r in rows) / n
    w = sum(wis(r["actual"], r["point"], r["lower50"], r["upper50"], r["lower80"], r["upper80"]) for r in rows) / n
    return {"n": n, "mae": mae, "coverage50": c50, "coverage80": c80, "width50": w50, "width80": w80, "wis": w}


def main(argv: list[str]) -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    fc = read_csv(CONF / "forecast.csv")
    m01 = read_csv(CONF / "monthly_report_count.csv")
    actual = {(r["product_code"], r["month"]): int(r["eligible_reports"]) for r in m01}

    scored = []
    for r in fc:
        if r["period"] not in SCORED_PERIODS or r["point"] == "" or r["lower80"] == "":
            continue
        y = actual.get((r["product_code"], r["target"]))
        if y is None:
            continue
        pt = float(r["point"])
        lo50, hi50, lo80, hi80 = (float(r[k]) for k in ("lower50", "upper50", "lower80", "upper80"))
        row = dict(r)
        row.update({"actual": y, "error": "%.6f" % (y - pt), "abs_error": "%.6f" % abs(y - pt),
                    "covered50": "true" if lo50 <= y <= hi50 else "false",
                    "covered80": "true" if lo80 <= y <= hi80 else "false",
                    "width50": "%.6f" % (hi50 - lo50), "width80": "%.6f" % (hi80 - lo80),
                    "wis": "%.6f" % wis(y, pt, lo50, hi50, lo80, hi80)})
        scored.append(row)
    write_csv(CONF / "forecast_scored.csv", scored)

    groups: dict[tuple, list[dict]] = {}
    for r in scored:
        groups.setdefault((r["product_code"], r["model"], int(r["horizon"]), r["period"]), []).append(r)
    out = []
    for (code, model, h, period), rows in sorted(groups.items()):
        g = golden_scores([{k: float(r[k]) for k in ("actual", "point", "lower50", "upper50", "lower80", "upper80")}
                           for r in rows])
        out.append({"product_code": code, "model": model, "horizon": h, "period": period, "n": g["n"],
                    "mae": "%.6f" % g["mae"], "coverage50": "%.6f" % g["coverage50"],
                    "coverage80": "%.6f" % g["coverage80"], "width50": "%.6f" % g["width50"],
                    "width80": "%.6f" % g["width80"], "wis": "%.6f" % g["wis"],
                    "mean_calibration_n": "%.1f" % (sum(int(r["calibration_n"]) for r in rows) / len(rows))})
    # scaled MAE against baseline A on the same cell
    base = {(r["product_code"], r["horizon"], r["period"]): float(r["mae"]) for r in out if r["model"] == "baseline_a"}
    for r in out:
        b = base.get((r["product_code"], r["horizon"], r["period"]))
        r["mae_scaled_vs_a"] = "" if not b else "%.6f" % (float(r["mae"]) / b)
    write_csv(CONF / "forecast_score.csv", out)
    print("scored %d rows into %d cells" % (len(scored), len(out)))
    for r in out:
        if r["horizon"] == 1:
            print("  %s %-10s h1 %-11s n=%2s MAE %8s scaled %6s cov80 %s WIS %8s"
                  % (r["product_code"], r["model"], r["period"], r["n"], r["mae"], r["mae_scaled_vs_a"],
                     r["coverage80"], r["wis"]))

    if "--promote" in argv:
        if cfg.get("promoted"):
            sys.exit("config/model.json already carries a promotion decision; it is not revisited")
        dev = {(r["product_code"], r["model"]): r for r in out if r["period"] == "development" and r["horizon"] == 1}
        codes = sorted({c for c, _ in dev})
        decision = {}
        for code in codes:
            a, b, c = dev.get((code, "baseline_a")), dev.get((code, "baseline_b")), dev.get((code, "candidate"))
            if not (a and b and c):
                decision[code] = {"model_in_use": "baseline_a", "reason": "a model has no development scores"}
                continue
            best_base = a if float(a["mae"]) <= float(b["mae"]) else b
            improve = float(c["mae"]) <= 0.90 * float(best_base["mae"])
            not_worse = float(c["wis"]) <= float(best_base["wis"])
            use = "candidate" if (improve and not_worse) else best_base["model"]
            decision[code] = {
                "model_in_use": use,
                "candidate_promoted": bool(improve and not_worse),
                "development_h1": {m: {"n": int(dev[(code, m)]["n"]), "mae": float(dev[(code, m)]["mae"]),
                                       "wis": float(dev[(code, m)]["wis"]),
                                       "coverage80": float(dev[(code, m)]["coverage80"])}
                                   for m in ("baseline_a", "baseline_b", "candidate")},
                "reason": ("candidate MAE %.2f vs best baseline (%s) %.2f: %s; WIS %.2f vs %.2f: %s"
                           % (float(c["mae"]), best_base["model"], float(best_base["mae"]),
                              "at least 10% better" if improve else "not 10% better",
                              float(c["wis"]), float(best_base["wis"]),
                              "not worse" if not_worse else "worse")),
            }
        cfg["promoted"] = decision
        cfg["promotion_decided_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("promotion written to config/model.json:")
        for code, d in decision.items():
            print("  %s -> %s (%s)" % (code, d["model_in_use"], d["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
