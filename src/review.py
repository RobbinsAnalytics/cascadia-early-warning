"""review.py -- PATH 1: the review queue (M-05) under the fixed rule (D9).

Under the model in use for each code, at horizon 1, over the locked and
recent targets: a month is flagged when its actual is above the 80% upper
range and at least five reports above the point. An episode is a run of at
least two consecutive flagged months; one run is one episode; a flagged final
month with no successor is pending. The rule is disabled for a code whose 80%
coverage in the locked test fell below 0.70 (numbers gate G5), and the queue
says so.

Writes data/conformed/review_queue.csv and data/conformed/review_workload.csv.
An empty queue is a valid result and is written as such.

    python src/review.py
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_model import read_csv, write_csv  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
CONF = REPO / "data" / "conformed"
CONFIG = REPO / "config" / "model.json"
MIN_EXCESS = 5.0
MIN_RUN = 2
EVALUATED = ("locked", "recent")
COVERAGE_FLOOR = 0.70


def flagged(row: dict) -> bool:
    return row["actual"] > row["upper80"] and (row["actual"] - row["point"]) >= MIN_EXCESS


def golden_episodes(rows: list[dict]) -> list[tuple[str, str, int]]:
    """rows: target, actual, point, upper80, in target order. Returns
    (episode_start, episode_end, months_in_episode) for every run of at least
    MIN_RUN consecutive flagged months. A trailing run of one is pending."""
    rows = sorted(rows, key=lambda r: r["target"])
    out, run = [], []
    for r in rows:
        if flagged(r):
            run.append(r["target"])
        else:
            if len(run) >= MIN_RUN:
                out.append((run[0], run[-1], len(run)))
            run = []
    if len(run) >= MIN_RUN:
        out.append((run[0], run[-1], len(run)))
    return out


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    promoted = cfg.get("promoted") or {}
    scored = read_csv(CONF / "forecast_scored.csv")
    scores = read_csv(CONF / "forecast_score.csv")
    queue, workload = [], []
    for code in sorted({r["product_code"] for r in scored}):
        use = promoted.get(code, {}).get("model_in_use")
        if not use:
            continue
        cov = [r for r in scores if r["product_code"] == code and r["model"] == use
               and r["horizon"] == "1" and r["period"] == "locked"]
        coverage80 = float(cov[0]["coverage80"]) if cov else None
        enabled = coverage80 is not None and coverage80 >= COVERAGE_FLOOR
        rows = [{"target": r["target"], "actual": float(r["actual"]), "point": float(r["point"]),
                 "upper80": float(r["upper80"])}
                for r in scored if r["product_code"] == code and r["model"] == use
                and r["horizon"] == "1" and r["period"] in EVALUATED]
        rows.sort(key=lambda r: r["target"])
        flags = [r["target"] for r in rows if flagged(r)]
        eps = golden_episodes(rows) if enabled else []
        pending = (rows and flagged(rows[-1]) and (len(rows) < 2 or not flagged(rows[-2])))
        for start, end, n in eps:
            excess = max(r["actual"] - r["point"] for r in rows if start <= r["target"] <= end)
            queue.append({"product_code": code, "model_in_use": use, "episode_start": start,
                          "episode_end": end, "months_in_episode": n, "max_excess_over_point": "%.1f" % excess,
                          "status": "closed" if end < rows[-1]["target"] else "open at the freeze"})
        workload.append({"product_code": code, "model_in_use": use, "rule_enabled": "true" if enabled else "false",
                         "locked_coverage80": "" if coverage80 is None else "%.3f" % coverage80,
                         "evaluated_months": len(rows), "flagged_months": len(flags),
                         "episodes": len(eps), "episodes_per_evaluated_month": "%.4f" % (len(eps) / len(rows)) if rows else "",
                         "pending_single_flag_at_end": "true" if (enabled and pending) else "false"})
        print("  %s  model %-10s  enabled %-5s  evaluated %2d  flagged %2d  episodes %d"
              % (code, use, enabled, len(rows), len(flags), len(eps)))
    write_csv(CONF / "review_queue.csv", queue or [{"product_code": "", "model_in_use": "", "episode_start": "",
                                                    "episode_end": "", "months_in_episode": "",
                                                    "max_excess_over_point": "", "status": "empty queue"}])
    write_csv(CONF / "review_workload.csv", workload)
    print("queue: %d episode(s) across %d codes" % (len(queue), len(workload)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
