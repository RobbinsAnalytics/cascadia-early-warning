# Golden fixtures

Written 2026-10-06 BEFORE any engine code existed, and committed failing. The
expected values were computed by hand from the decision record (D6 to D9) and
the metric register's definitions; `src/test_golden.py` only compares, on both
derivation paths (Path 1, the engine under `src/`; Path 2, the independent
re-derivation in `src/validate_measures.py`).

| Fixture | Decision | What is hand-specified |
|---|---|---|
| `golden_series.csv`, `golden_expected_baselines.csv` | D6 | A 48-month series, `count = 100 + 10*s(month) + t` with `s = 0,1,2,3,2,1,0,-1,-2,-3,-2,-1` and `t` months since 2020-01; trailing three-month mean and same-month-last-year points at chosen origins, with the rows that must be absent when history is too short |
| `golden_ets_states.csv`, `golden_expected_ets.csv` | D6 | Final ETS(A,Ad,A) states and the h-step point in log space: `level + trend * sum(phi^j, j=1..h) + s[(h-1) mod 12]`, seasonals oldest first for months T-11..T |
| `golden_review_input.csv`, `golden_expected_review.csv` | D9 | Twelve months of actual, point and 80% upper; two episodes, one of which ends on a month that is above the range but fewer than five reports above the point, plus a single flagged month that is not an episode, and a flagged final month that is pending rather than an episode |
| `golden_lag_reports.csv`, `golden_expected_lag.csv` | M-02 | Seven reports: lags of 1, 3, 4, 8 and 14 months, one missing event date, one negative lag |
| `golden_score_input.csv`, `golden_expected_scores.csv` | D8 | Three forecast rows; MAE, coverage at 50% and 80% (inclusive at the bound), mean widths, and the weighted interval score with K = 2 central intervals, weights 1/2 for the point and alpha/2 for each interval |

Lag in months is `(received year*12 + month) - (event year*12 + month)`;
`within_k` means lag between 0 and k inclusive. A negative lag is counted
separately and never in a `within_k` column.
