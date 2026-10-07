# Cascadia Early Warning

Which product codes are reporting as expected, and which deserve a closer
look? A public-data module on FDA medical device reports (openFDA
`/device/event`) for seven cardiovascular product codes spanning Classes II
and III: a forecast of reports received per month with ranges, a locked
held-out test of whether ranges like them held, and a fixed review rule that
turns departures from expectation into a human review queue. Aggregate only; no firm is named;
report counts are not incident rates or measures of device safety.

Pages: `docs/index.html` (the module) and `docs/case-study.html` (the case
study), published to `https://www.robbinsanalytics.com/cascadia-early-warning/`
once approved. Both are generated from the frozen tables by
`src/build_page.py`, from `docs/template.html` and
`docs/case-study-template.html`.

## Rebuild

From the committed freeze and offline. The execution policy on the build
machine is Restricted, so name the policy for the one process:

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 build      # build_page: the pages, from the frozen tables
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 validate   # test_golden, validate_measures, validate --prove-failable, validate_freeze
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 all        # validate, build, validate; stops at the first failure
```

`build` does not re-run the engine stages (`build_model`, `forecast`,
`score`, `review`, `recall_context`): each writes tables the freeze gate
protects, and the locked forecast stage refuses to run twice. The build
session ran them directly, and the git log is their record. `build` reads the
gitignored DuckDB record table `data/conformed/early_warning.duckdb` for two
facts no committed table holds (distinct report totals, summary-report
composition). A fresh clone lacks it: restore the staged pages with
`src/acquire.py --restore`, then run `src/build_model.py`, which rebuilds the
table and rewrites the frozen conformed tables it produces; the freeze gate
must then show them unchanged.

`run.ps1` names the venv interpreter by path (`.venv\Scripts\python.exe`,
created from `C:\Users\Ajayr\AppData\Local\Python\pythoncore-3.14-64\python.exe`
with `--system-site-packages`; `requirements.txt` adds statsmodels). Bare
`python` on the build machine is an empty interpreter and is never used.

`run.ps1 acquire` re-pulls the source. It is a deliberate refresh and
overwrites the freeze; nothing else here makes a network request.

The forecast harness runs in two stages whose order the git log enforces:
`forecast.py --stage development`, then `score.py --promote` (its own commit),
then `forecast.py --stage locked`. The locked stage refuses to run a second
time once locked rows exist; it was run twice before any locked row was
committed, to repair a harness defect (decision record D17), and the
committed history carries one result.

## What is where

| Path | What |
|---|---|
| `governance/source-register.md`, `data/raw/manifest.json` | what was pulled, when, and what it hashes to |
| `governance/decision-record.md` | D1 onward, each with its counterfactual and what carries it |
| `governance/pre-registration.md`, `config/model.json` | the harness and the rule, fixed before any forecast row |
| `governance/metric_register.md` | M-01 to M-07 with owner, lineage, population, limits, version, reviewer |
| `governance/numbers-gate.md` | the bands stated before the measures ran, and the results |
| `governance/validation_report.md` | the domain gate and the proof the checks can fail |
| `governance/exclusion-receipt.md`, `exclusion-receipt-records.md` | the private list's hash and the counts removed, no names |
| `governance/artifact-calendar.md` | reporting-system events that move the series |
| `governance/chart-review.md`, `pre-panel-notes.md` | the chart review under VIZ-PRINCIPLES v2.8 and the reading panel |
| `tests/golden/` | hand-specified expectations written before the engines |
| `data/conformed/` | the published tables; `early_warning.duckdb` is the record grain, rebuilt, not committed |

The record-level responses stay in `data/raw/staging/` (gitignored) and the
freeze is asserted by hash; see `CLAUDE.md`.

## The live edge (weekly, never published)

```
.venv\Scripts\python.exe src\pull_live_edge.py        # seven keyless requests; data/live/ and run_history.jsonl
.venv\Scripts\python.exe src\reconcile_live_edge.py   # health.json, reconciliation.md, then the page
.venv\Scripts\python.exe src\test_live_edge.py        # offline tests of the pull
```
