"""cohort_gate.py -- the day-one cohort gate (D2), from the S-02 count series.

Stage A, from counts alone, before any record is extracted:
    complete_months   months in the training span (2016-01 to 2023-12) with at
                      least one report received; the gate asks for 36 or more
    raw_training      reports received 2016-01 to 2023-12, before exclusion
    raw_window        reports received 2016-01 to 2026-08
Stage B, written by src/build_model.py after the private exclusion:
    eligible_training reports remaining in the training span; the gate asks
                      for 120 or more

A code is forecast only if both stages pass. Codes that fail are counted,
reported and never forecast. One passing code is a reduced release; none is a
feasibility finding, published as such.

Writes data/conformed/cohort_gate.csv (stage A columns; stage B columns are
filled in by build_model.py). Offline.

    python src/cohort_gate.py
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from acquire import COHORT, COUNTS, REPO, WINDOW_END, WINDOW_START  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TRAIN_START, TRAIN_END = "201601", "202312"
MIN_COMPLETE_MONTHS = 36
MIN_ELIGIBLE_TRAINING = 120
OUT = REPO / "data" / "conformed" / "cohort_gate.csv"


def monthly(code: str) -> dict[str, int]:
    p = COUNTS / ("%s_date_received.json" % code)
    data = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for r in data["results"]:
        out[r["time"][:6]] = out.get(r["time"][:6], 0) + r["count"]
    return out


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as fh:
            existing = {r["product_code"]: r for r in csv.DictReader(fh)}
    rows = []
    for code in COHORT:
        m = monthly(code)
        train = {k: v for k, v in m.items() if TRAIN_START <= k <= TRAIN_END}
        window = {k: v for k, v in m.items() if WINDOW_START[:6] <= k <= WINDOW_END[:6]}
        complete = sum(1 for v in train.values() if v > 0)
        prev = existing.get(code, {})
        row = {
            "product_code": code,
            "complete_months_training": complete,
            "raw_training_reports": sum(train.values()),
            "raw_window_reports": sum(window.values()),
            "stage_a_pass": "true" if complete >= MIN_COMPLETE_MONTHS else "false",
            "eligible_training_reports": prev.get("eligible_training_reports", ""),
            "stage_b_pass": prev.get("stage_b_pass", ""),
            "forecast": prev.get("forecast", ""),
        }
        rows.append(row)
        print("  %s  complete months %2d/96  raw training %7d  raw window %7d  stage A %s"
              % (code, complete, row["raw_training_reports"], row["raw_window_reports"],
                 "PASS" if row["stage_a_pass"] == "true" else "FAIL"))
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    n = sum(1 for r in rows if r["stage_a_pass"] == "true")
    print("stage A: %d of %d codes pass (%d complete months required)" % (n, len(rows), MIN_COMPLETE_MONTHS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
