# Pre-registration

*Written 2026-10-06, before any forecast row existed. Owner: Aaron Robbins.
The git log of this file and of `config/model.json` is the proof of order,
and the commit hash of this file is printed on the page. Nothing below is
edited after the first forecast row is written; corrections, if any, are
appended under "Amendments" with their date and reason.*

Read with `config/model.json`, which fixes the harness in machine-readable
form, and `governance/decision-record.md` D5 to D11, which carry the reasons.
This document fixes what the page will report and how it will be read, so
that a weak result is a finding and not a failure.

## 1 · What is fixed

- **Target.** M-01, eligible reports per product code per receipt month.
- **Horizons.** 1 and 3 months ahead of the origin.
- **Periods.** Warmup targets 2019-01 to 2021-12 (calibration only); development
  targets 2022-01 to 2023-12 (selection); locked targets 2024-01 to 2025-12
  from origins at or after 2023-12 (the test, run once); recent targets
  2026-01 to 2026-08 (origins at or after 2025-12); outlook from origin
  2026-08.
- **Models.** Baseline A, trailing three-month mean; baseline B, the value
  twelve months before the target; the candidate, ETS with additive error,
  damped additive trend and additive seasonality of period 12 on
  `log1p(count)`, back-transformed. The candidate's form never changes; its
  parameters are refitted at every origin.
- **Ranges.** Empirical quantiles of the model's own signed errors over the
  36 most recent targets elapsed at the origin: 25th and 75th for the 50%
  range, 10th and 90th for the 80% range. No range is drawn on fewer than 12
  errors.
- **Scores.** MAE, MAE scaled by baseline A, coverage at both levels
  (inclusive at the bound), mean widths, the weighted interval score with
  weights 1/2 for the point and alpha/2 per interval, by code, horizon, model
  and period, never averaged across codes.
- **Promotion.** Decided on development targets at horizon 1 only: the
  candidate is the model in use for a code when its MAE is at most 0.90 times
  the better baseline's and its WIS is not worse; otherwise the better
  baseline is in use. Written into `config/model.json` in its own commit
  before any locked-period row exists.
- **The review rule.** Under the model in use at horizon 1, a target month is
  flagged when its actual is above the 80% upper range and at least five
  reports above the point. An episode is a run of at least two consecutive
  flagged months; one run is one episode; a flagged final month with no
  successor is pending. Evaluated over locked and recent targets. The rule is
  disabled for a code whose locked-test 80% coverage is below 0.70, and the
  queue says so.
- **The five-report floor is a workload heuristic**, chosen so that a
  departure of a handful of reports in a small series never opens an
  episode. It is not a calibrated threshold and the page says so.

## 2 · What the review rule would do by chance

If a model's 80% ranges are calibrated and its errors are independent across
months, a single month lands above the upper range about one time in ten, and
two consecutive months about one time in a hundred. **The expectation under
no change is therefore about one episode start per hundred evaluated months
per code**, before the five-report floor removes some of those. Across seven
codes over the 32 evaluated months (24 locked and 8 recent), that is about
two episodes by chance. The queue's workload is read against this figure, and
the numbers gate (G6) stops the build if the rule flags more than three months
in ten.

## 3 · The one pre-registered recall count

**Definition.** Among the recall events in `data/conformed/recall_context.csv`
whose enforcement classification is Class I, whose initiation date falls in
the evaluated span (2024-01 to 2026-08) and whose product code is a forecast
code: the number of review episodes (from `review_queue.csv`) whose start
month falls in the eighteen months before the initiation month, that is, in
`[initiation month - 18, initiation month - 1]` inclusive, for the same
product code. Reported with:

- the number of such Class I initiations;
- the number of those initiations preceded by at least one episode start in
  its window;
- the number of episodes in the queue whose start falls in at least one such
  window (an episode counts once even if it falls in two windows, which can
  happen where one code has repeated recalls; windows are never truncated);
- the same two initiation counts under the trivial always-flag rule, which
  flags every month, precedes every initiation that has an evaluated month in
  its window, and costs one flag per month; it is the reminder that
  "preceded" alone means nothing.

**Why this count and not a hit rate.** A back-test with hits, misses, false
alarms, lead times and a permutation null is the right instrument and it is
not in this build: the recall work was bounded in the plan to a dated timeline
and one count, and the shuffled-dates null that would turn the count into a
test is the first scope cut and a build-forward candidate. The count is
published as association only. It cannot say the rule predicted anything.

**What else is published beside it, and is not selected on.** Every in-scope
recall event in the window, with class where the enforcement endpoint has it,
initiation and classification dates, the root cause as FDA recorded it, the
number of product records, and a flag for whether FDA's recorded reason text
mentions reports or complaints (the text itself is never published; it can
carry brand names). Root causes are not filtered: a filter chosen after seeing
the data would be selection, and the count is already not a test.

**No published multi-code comparison exists.** The only published figures on
MAUDE signals before a recall are single-device: ten months (FDA's own
data-mining white paper) and eighteen months (a 2016 dissertation on a lead
recall). The page states that it has nothing to compare its count against.

## 4 · Known-answer recovery

Before anything is computed from the recall timeline, the derived event set
must recover, unprompted, the fourteen Class I recall events in these product
codes that the research verified by recall event number and initiation date.
They are listed in `data/reference/known_events.csv` by event number, product
code and initiation date, with no firm or brand. `src/validate.py` fails if
any is missing from `recall_context.csv` or carries a different initiation
date. This is a check on the join, not on the rule.

## 5 · The as-seen caveat

The back-test reads the frozen snapshot of 2026-10-06 and uses `date_received`
to decide what was knowable at each origin. That approximates what a reader
would have seen on that date; it is not the same thing. openFDA holds the
most recent version of each report and replaces records in place, so a
report's receipt date is reliable but its presence in a past month's total
is not guaranteed to match what the source showed then. True as-seen
vintages accrue only from a live edge that stores each run's series, which
is Phase 5 if reached.

## 6 · Leakage and surges

A recall itself causes reports: reports whose `remedial_action` includes
"Recall" are counted per code and month in `monthly_remedial_recall.csv` and
shown beside the review queue, so a post-recall surge can be read as one.
Nothing is removed from the series on that account; the forecast target is
reports received, whatever caused them.

## 7 · Scope cuts, in order

1. The shuffled-dates null test (not built; build-forward).
2. The live edge (Phase 5, only if Phases 1 to 4 finish by day 6).
3. Horizon-3 charts (a table stands in if the page runs long).
4. PYX, if its stage B gate fails on eligible training reports; its series
   is thin before 2023 and a reduced cohort is published as such.

## Amendments

None.
