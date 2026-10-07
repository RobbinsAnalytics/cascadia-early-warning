# Certified measure register

*Phase 2 artifact. Owner of every measure below: **Aaron Robbins**. Established
2026-10-06. Receipts frozen through **2026-08-31**, retrieved 2026-10-06. Every
measure carries a written definition, a named owner, outputs, lineage to source
fields, a population, a statistic, stated limits, a version and a reviewer. The
values live in `data/conformed/`; this document defines them and does not
restate them. A figure that appears in any rendered output and is not defined
here is not certified and must not be published.*

**Independent validation.** `src/validate_measures.py` re-derives every
certified cell down a separately written path: DuckDB SQL over the staged
records for the counts, a hand-written recurrence for the candidate's
mechanics, and its own implementations of the scores and the review rule,
written from this register and the decision record and never by reading the
engine. **Nothing is published unless that script exits zero.** A measure that
only agrees with itself has not been validated.

**Three words that do the work.** *Report* means one `mdr_report_key`, which
openFDA holds as the most recent version of a submission; a follow-up to the
same event is the same report. *Eligible* means not removed by the private
exclusion (D3). *Receipt month* means the calendar month of `date_received`,
the date FDA received the report, which is the only date every record carries
and the only date that says what was knowable when.

---

## M-01 · Eligible reports per code per receipt month

> **Definition.** The number of distinct eligible reports whose device array
> carries the product code, by receipt month. A report with two devices under
> the same code counts once; a report with devices under two cohort codes
> appears in both codes' series, and series are never summed across codes.

| | |
|---|---|
| **Owner** | Aaron Robbins |
| **Outputs** | `data/conformed/monthly_report_count.csv` (`raw_reports`, `excluded_reports`, `eligible_reports`, `series_reports` from S-02) |
| **Lineage** | S-01 `mdr_report_key`, `date_received`, `device[].device_report_product_code`; S-02 `count=date_received` per code; the exclusion audit (private) |
| **Population** | Receipt months 2016-01 to 2026-08, the seven cohort codes |
| **Statistic** | Count |
| **Certified** | Yes. `raw_reports` reconciles to the S-02 series month by month with zero variance, and `eligible_reports = raw_reports - excluded_reports`, so every unit of variance between the series and the published count is an excluded report, counted in the receipt |
| **Version** | 1.0, 2026-10-06 |
| **Reviewer** | Not yet reviewed; the reading panel reviews the charts, not the register |

**Limits.**
- **A count of reports, not of events and not of devices.** FDA's own words:
  MDR data alone cannot establish rates, evaluate a change in rates over time,
  or compare rates between devices. Nothing here is a rate.
- **Receipt timing is a filing rhythm.** Manufacturers batch; the source shows
  month-end pile-ups. The series is honest about when FDA received reports and
  says nothing about when events happened (that is M-02's job).
- **The most recent months are complete only as of `meta.last_updated`
  2026-09-29.** Reports received in August 2026 and loaded after that date are
  not in this freeze. The page says so.
- **These codes are ineligible for malfunction summary reporting**, so one
  record is one report across the whole window; the classification extract
  carries the eligibility flag per code as evidence.

## M-02 · Lag-matched counts and event-to-receipt lag

> **Definition.** For each event month (`date_of_event`), the number of
> eligible reports received within 3, 6 and 12 months of that month, where
> lag is `(receipt year * 12 + month) - (event year * 12 + month)` and
> "within k" means a lag from 0 to k inclusive. Reports with no event date
> and reports received before their event month are counted separately and
> never inside a within-k column.

| | |
|---|---|
| **Owner** | Aaron Robbins |
| **Outputs** | `data/conformed/monthly_lag_matched.csv` |
| **Lineage** | S-01 `date_of_event`, `date_received`, `mdr_report_key`, `device[].device_report_product_code` |
| **Population** | Event months 2016-01 to 2026-08, eligible reports, the seven cohort codes |
| **Statistic** | Count, and the share of a month's reports that had arrived within k months |
| **Certified** | The computation is certified; the figure is a diagnostic, never proof of what was publicly available at any date |
| **Version** | 1.0, 2026-10-06 |
| **Reviewer** | Not yet reviewed |

**Limits.**
- **The event date is the reporter's actual or best estimate**, missing on a
  share of records that is published beside the figure, and absent before
  2006.
- **A like-for-like view, not a nowcast.** Comparing event months by what had
  arrived within the same k months removes the right-censoring of recent
  months without modelling anything. It does not estimate what will arrive.
- **Recent event months are shaded incomplete on the page** for every k whose
  window has not yet elapsed at the freeze date.

## M-03 · Forecasts and ranges per code and horizon

> **Definition.** At each origin month, for horizons 1 and 3, the point
> forecast of M-01 for the target month from each of three models (D6), with
> 50% and 80% ranges from the empirical quantiles of that model's signed
> errors over the 36 most recent elapsed targets (D7) and the number of
> errors those quantiles rest on.

| | |
|---|---|
| **Owner** | Aaron Robbins |
| **Outputs** | `data/conformed/forecast.csv` (issue date, origin, target, horizon, model, point, lower50, upper50, lower80, upper80, calibration_n, period; the candidate rows also carry the fitted parameters and final states) |
| **Lineage** | M-01 `eligible_reports` at or before the origin; `config/model.json` |
| **Population** | Origins 2018-12 to 2026-08 for the codes that pass the cohort gate; periods warmup, development, locked, recent, outlook |
| **Statistic** | Point and quantile ranges |
| **Certified** | **No.** A forecast is a computation, not a fact. What is certified is that the mechanics are re-derived: the baselines in SQL, the candidate's point from its exported states by an independent recurrence, the quantiles from the exported errors |
| **Version** | 1.0, 2026-10-06 |
| **Reviewer** | Not yet reviewed |

**Limits.**
- **A forecast of reports received, nothing else.** It says what volume FDA
  should expect to receive, not what will happen to anyone.
- **The outlook for 2026-09, issued in 2026-10, is an elapsed-period
  estimate**, not a forecast: the month had ended before the figure was
  issued, and the source had not yet loaded it. It is labelled so.
- **Ranges are empirical and only as good as the last 36 errors.** The
  calibration count is published with every range, and a range resting on
  fewer than 12 errors is not drawn.

## M-04 · Scores

> **Definition.** By code, horizon, model and period: mean absolute error;
> that MAE divided by baseline A's MAE on the same rows (scaled MAE);
> empirical coverage of the 50% and 80% ranges (a value on the bound is
> covered); the mean width of each range; the weighted interval score over
> the point and the two central ranges with weights 1/2 and alpha/2; and the
> number of rows scored.

| | |
|---|---|
| **Owner** | Aaron Robbins |
| **Outputs** | `data/conformed/forecast_score.csv` |
| **Lineage** | M-03 rows joined to M-01 actuals on (code, target) |
| **Population** | Development (targets 2022-01 to 2023-12), locked (targets 2024-01 to 2025-12 from origins at or after 2023-12) and recent (targets 2026-01 to 2026-08), separately |
| **Statistic** | As defined; nothing is averaged across codes |
| **Certified** | The computation is certified: `src/validate_measures.py` recomputes every score from the exported predictions and actuals |
| **Version** | 1.0, 2026-10-06 |
| **Reviewer** | Not yet reviewed |

**Limits.**
- **The locked test ran once** (D5). Its scores are the answer, whatever they
  are; a weak result is published as plainly as a strong one.
- **Scaled MAE above 1 means the candidate did worse than a trailing mean**,
  and the page says so where it happens.

## M-05 · Review queue

> **Definition.** Under the model in use for a code, an episode is a run of
> consecutive target months, at least two long, in each of which the actual
> exceeds the 80% upper range and exceeds the point by at least five reports
> (D9). One run is one episode. A flagged final month with no successor is
> pending, not an episode. Workload is episodes per evaluated month.

| | |
|---|---|
| **Owner** | Aaron Robbins |
| **Outputs** | `data/conformed/review_queue.csv`, `data/conformed/review_workload.csv` |
| **Lineage** | M-03 (horizon 1, model in use) and M-01 actuals |
| **Population** | Target months in the locked and recent periods |
| **Statistic** | Episodes, months in episode, episodes per evaluated month |
| **Certified** | The computation is certified; the rule itself is a decision (D9), re-derived independently |
| **Version** | 1.0, 2026-10-06 |
| **Reviewer** | Not yet reviewed |

**Limits.**
- **An empty queue is a valid result.** The page shows the rule and the
  evaluated months whether or not anything was flagged.
- **A flag is a departure from expected reporting volume**, nothing more. It
  does not say why, and it is not a statement about any device or firm.
- **A code whose 80% coverage in the locked test fell below 70% has its rule
  disabled** (numbers gate G5), and the queue says so for that code.

## M-06 · Recall context

> **Definition.** In-scope recall events: recall records whose product code is
> a cohort code, deduplicated to events on `res_event_number`, with the
> firm's initiation date, FDA's classification date, the root cause as FDA
> recorded it, the class from the enforcement endpoint where the event is
> there, and the count of product records in the event. No firm name. And one
> pre-registered count, defined in `governance/pre-registration.md` before it
> was computed: review episodes whose start falls in the 18 months before a
> Class I initiation, with the trivial always-flag rule beside it.

| | |
|---|---|
| **Owner** | Aaron Robbins |
| **Outputs** | `data/conformed/recall_context.csv`, `data/conformed/recall_count.json` |
| **Lineage** | S-05 `product_code`, `res_event_number`, `event_date_initiated`, `event_date_posted`, `root_cause_description`, `k_numbers`, `pma_numbers`; S-04 `event_id`, `classification` |
| **Population** | Recall events initiated 2016-01-01 to 2026-08-31 with a cohort product code |
| **Statistic** | Count; the pre-registered count is association only |
| **Certified** | The timeline is certified as a transcription of the two endpoints; the count is pre-registered and is not evidence of prediction |
| **Version** | 1.0, 2026-10-06 |
| **Reviewer** | Not yet reviewed |

**Limits.**
- **Class is knowable only after FDA classifies**, about six to eight weeks
  after initiation, and only from 2012 in the enforcement endpoint.
- **A recall is a firm's or FDA's action, not an event rate**, and it can
  itself cause a reporting surge. The timeline is retrospective context for
  the review queue, never its validation; the shuffled-dates null test that
  would make the count a test is a build-forward candidate.

## M-07 · Live edge (optional, not yet built)

Each elapsed target month's actual against the forecast issued for it,
appended per run. Defined here so that the measure exists before any run; not
certified until a run has written it.

---

## Deliberately not certified

**Any count per manufacturer, brand or firm.** The module is aggregate only
(D3). The exclusion receipt publishes counts removed per field, no names.

**Any rate, incidence, risk or safety statement.** No denominator exists in
the source, and FDA says MDR counts cannot be used as rates.

**Event counts.** `noe_summarized` and the event date are not reliable enough
to count events; reports are counted, and the register says so in M-01.

**A nowcast of recent event months.** M-02's lag-matched counts are the
like-for-like view; a modelled completion factor is a build-forward candidate.

**The outlook figure for an elapsed period as a forecast.** It is published,
labelled an estimate, and never scored as a forecast.
