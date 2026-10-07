# Decision record - Cascadia Early Warning

*Owner: Aaron Robbins. Opened 2026-10-06, Layer 0 (before any data was pulled).
Decisions D1 to D13 restate the approved build plan so that the repository
carries them; each names what carries it. Later layers append and never
rewrite. A decision that never becomes an instruction is not adopted.*

---

## D1 · The target is a count of reports, never a rate, a risk or an event

The forecast target is the number of distinct `mdr_report_key` values with a
given product code in each receipt month (`date_received`). One report with
several devices under the same code counts once; a report whose devices carry
two cohort codes appears in both codes' series, and series are never summed.
Horizons are 1 and 3 months ahead.

*Counterfactual:* an event count (`noe_summarized`, `date_of_event`) would be
closer to what a reader wants and is not reliably observable: the event date is
missing on about one record in seven and summary reports stand for many events.
Rates need denominators the source does not carry, and FDA says MDR data cannot
establish rates. A report count is the only number here that can be certified.

**Carried by:** `governance/metric_register.md` M-01; `src/build_model.py`;
the page's limits section.

## D2 · Cohort: seven Cardiovascular Class III codes, gated on day one

DSQ, OZD, PYX, NPT, NIK, LWS, DSP: implanted or life-sustaining cardiovascular
devices, ineligible for malfunction summary reporting, so one record is one
report across the whole window. Each code is forecast only if it passes the
cohort gate: 36 complete months of history and at least 120 eligible training
reports. Codes that fail are counted and reported, never forecast. One passing
code is a reduced release; none passing is a feasibility finding, published as
such, never a flattering substitute.

*Counterfactual:* contact-lens codes (LPL, LPM) are a clean panel with no
excluded firm but became summary-eligible on 2018-08-17 and again changed
format on 2024-08-29, so one record stops meaning one report mid-window.
Diabetes codes are high-volume, summary-eligible and near-firm series.

**Carried by:** `src/acquire.py` (`COHORT`); `data/conformed/cohort_gate.csv`;
`governance/numbers-gate.md`.

## D3 · Exclusion by a private token list, with a public receipt

A list of firm-name tokens lives at `governance/exclusion-list.local.txt`,
gitignored. Two things derived from it are committed: its SHA-256 and the set
of product codes those firms have cleared, approved, recalled or listed, which
are excluded from the cohort outright. Inside the cohort, any report whose
manufacturer or brand fields match the list is removed whole, and the counts
removed per field are published. No firm name appears in anything committed or
rendered, and the reason for the list is not stated in the repository.

*Counterfactual:* publishing the list would make the exclusion auditable and
would name firms the module exists to stay at arm's length from. The receipt
is the audit.

**Carried by:** `.gitignore`; `src/derive_exclusion_codes.py`;
`data/reference/excluded_product_codes.csv`; `governance/exclusion-receipt.md`;
`src/build_model.py` (`exclusion_audit`, private; `exclusion_receipt`, public).

## D4 · The freeze is asserted by hash for the record-level payloads

Record-level responses carry narratives, patient arrays and addresses and run
to hundreds of megabytes. They stay in gitignored staging; `data/raw/manifest.json`
holds a SHA-256 per response and is committed; `src/validate.py` recomputes
every hash. The count series, the classification extract and the manifest are
committed outright. This is the same departure from PRINCIPLES rule 1's
mechanism that `cascadia-matter-ledger-analytics` records.

*Counterfactual:* committing the payloads would put personal narrative text in
a public repository and would make the freeze gate churn on files git should
not hold.

**Carried by:** `.gitignore`; `governance/freeze.toml`; `CLAUDE.md`;
`governance/source-register.md`.

## D5 · Chronology: rolling origins, selection frozen at 2023-12, one locked test

History 2016-01 to 2021-12. Model selection on origins in 2022-01 to 2023-12,
with the choice of candidate parameters frozen in `config/model.json` at
2023-12 and committed before any forecast row exists. The locked test is
origins at or after 2023-12 targeting 2024-01 to 2025-12, run once. Recent
check: 2026-01 to 2026-08. Forecast rows are written before actuals are joined,
and every row's origin precedes its target.

*Counterfactual:* selecting on the test period, or re-running the test after
seeing it, is the failure this module exists to show it did not make.

**Carried by:** `config/model.json`; `governance/pre-registration.md`;
`src/forecast.py`; `git log` of those files; `src/validate.py` (chronology
check).

## D6 · Two baselines and one fixed candidate

Baseline A: trailing three-month mean. Baseline B: same month last year.
Candidate: ETS with additive error, damped additive trend and 12-month
additive seasonality, fitted on `log1p(count)` and back-transformed. The
candidate's form is fixed before the test; only its fitted parameters vary
by origin.

*Counterfactual:* a model chosen from a menu after seeing the test is a model
chosen on the test.

**Carried by:** `config/model.json`; `src/forecast.py`; `tests/golden/`.

## D7 · Intervals are empirical, from the last 36 elapsed errors

The 50% and 80% ranges at each origin are the quantiles of the signed errors of
that model and horizon over the most recent 36 elapsed target months, added to
the point forecast. The calibration count is published with every range.

*Counterfactual:* model-implied intervals assume the model's error structure is
right, which is the thing under test.

**Carried by:** `src/forecast.py`; `data/conformed/forecast.csv`
(`calibration_n`).

## D8 · Scores, and the promotion rule

MAE and MAE scaled by baseline A's MAE; weighted interval score at 50% and 80%;
empirical coverage and mean width at each level; by code, horizon and period
(development and locked, separately). The candidate is promoted over the
baseline only if its scaled MAE improves by at least 10% without a worse WIS,
judged on the development period before the test, and the judgement is
recorded in `config/model.json`.

*Counterfactual:* promoting on any improvement rewards noise.

**Carried by:** `src/score.py`; `src/validate_measures.py` (independent
recomputation); `config/model.json` (`promoted`).

## D9 · The review rule

An episode opens when two consecutive target months have actuals above the
80% upper range and at least five reports above the point forecast, under the
model in use; one episode per run per code; an empty queue is a valid result.
Workload is published as episodes per evaluated month.

*Counterfactual:* a single-month trigger fires on the receipt pile-ups the
source is known for.

**Carried by:** `src/review.py`; `data/conformed/review_queue.csv`;
`tests/golden/`.

## D10 · Latency is labelled, never hidden

Receipts run through 2026-08-31 and the API's own `meta.last_updated` is
recorded. A figure for 2026-09 issued in 2026-10 is an elapsed-period estimate,
not a forecast, and is labelled so. The 36-day gap between the newest receipt
and the retrieval date is stated on the page.

**Carried by:** the page's first section; `data/raw/manifest.json`
(`meta_last_updated`).

## D11 · Recall context is bounded and pre-registered

A dated timeline of in-scope recall events (deduped on event number, class
from the enforcement endpoint, initiation date, root cause, no firm names) and
one pre-registered count: review episodes whose start falls in the 18 months
before a Class I initiation, with the trivial always-flag rule beside it.
Association only. The shuffled-dates null is the first scope cut and is a
build-forward candidate.

**Carried by:** `governance/pre-registration.md`; `src/recall_context.py`;
`data/conformed/recall_context.csv`.

## D12 · The interpreter is named by path

`.venv/Scripts/python.exe`, created from
`C:\Users\Ajayr\AppData\Local\Python\pythoncore-3.14-64\python.exe` with
`--system-site-packages`, plus `statsmodels` pinned in `requirements.txt`.
Bare `python` on this machine is an empty 3.14.7.

**Carried by:** `run.ps1`; `CLAUDE.md`; the scheduled-task file if Phase 5 is
reached.

## D13 · The name is Cascadia Early Warning

Decided by Aaron 2026-10-06. The page earns the name: the review rule is the
warning, the locked test is its proof, and the limits say it flags reporting
change and predicts nothing about safety.

**Carried by:** the page title; the repository name.
