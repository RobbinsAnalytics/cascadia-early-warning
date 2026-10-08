# Cascadia Early Warning - what an agent needs to know

A public-data module that forecasts the next month's volume of FDA medical
device reports for a small cohort of product codes, shows whether its forecasts
earned trust on a locked held-out period, and turns departures from
expectation into a human review queue. Source is openFDA `/device/event`,
`/device/recall`, `/device/enforcement` and `/device/classification`. It
publishes `docs/` to `https://www.robbinsanalytics.com/cascadia-early-warning/`
once Aaron approves; no remote exists until he creates it.

**The estate's session rules - surfaces, guards, and the traps that have each
cost a session - are at
`C:\Projects\cascadia-standards\governance\SESSION-RULES.md`.** Read §1–§7 and
stop at the line. What gets published is governed by `PRINCIPLES.md` in the
same directory. This file carries only what is true of this repo.

## Three hard constraints, before anything else

**1 · No firm name anywhere committed or rendered.** The module is aggregate
only: report counts per product code per month. No manufacturer ranking, no
brand series, no chat assistant, no classifier. A private token list at
`governance/exclusion-list.local.txt` (gitignored, never committed) removes
whole reports whose manufacturer fields match it, and excludes a derived set of
product codes; what is committed is the file's SHA-256, the derived code set,
and a receipt of counts per field. The reason the list exists is not stated
anywhere in this repository and is not to be added.

**2 · Report counts are not incident rates, event rates or measures of device
safety.** FDA says so in as many words and the page quotes it. Nothing here
may present a count, a forecast or a review flag as a statement about risk,
causation, or any firm or device. The review rule flags reporting change; it
predicts nothing about safety.

**3 · Chronology is enforced by the git log, not by promise.** `config/model.json`
and `governance/pre-registration.md` are committed before the first forecast
row exists; every forecast row's origin precedes its target; the locked test
(2024-01 to 2025-12) is frozen once (D17 records the one pre-commit repair) and its scores are not revisited. If a result
looks wrong, say so in the report; do not re-fit.

## The freeze

**The data is frozen with receipts through 2026-08-31, retrieved 2026-10-06,
and that date is a claim made out loud.** `governance/source-register.md`
holds every request, its retrieval time, the API's own `meta.last_updated`,
and a SHA-256 per response. `src/acquire.py` re-pulls the source and
**overwrites the freeze** - only run it to deliberately refresh. Everything
else rebuilds from the committed snapshot, offline; `run.ps1 build` makes no
network request.

**`run.ps1 build` rebuilds the pages and nothing else.** The engine stages
(`build_model.py`, `forecast.py`, `score.py`, `review.py`,
`recall_context.py`) each write frozen tables and are deliberately not in it;
the build session ran them directly and the git log records what they wrote.
`run.ps1 validate` runs the four gates; `run.ps1 all` runs validate, build,
validate and stops at the first failing stage with that stage's exit code.
`build` reads the gitignored DuckDB record table for the distinct report
totals and the summary-report composition, so a fresh clone needs the staged
pages restored and `src/build_model.py` run first (it rewrites the frozen
conformed tables, which the freeze gate must then show unchanged).
The execution policy here is Restricted, so invoke it as
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 <task>`.
Until 2026-10-07 the wrapper passed no arguments to any stage (its parameter
was named `$args`, which inside the body is PowerShell's empty automatic
variable), so no stage had ever run through it; never name a parameter after
an automatic variable.

**This module departs from PRINCIPLES rule 1's mechanism, deliberately and on
the record.** Rule 1 says commit the raw response. The record-level payloads
carry narratives, patient arrays and addresses and run to hundreds of
megabytes, so `data/raw/staging/` is gitignored and **the freeze is asserted by
hash**: `data/raw/manifest.json` is committed with a SHA-256 per staged file,
and `src/validate.py` recomputes every one. The same departure, for the same
reason, is on the record in `cascadia-matter-ledger-analytics`. A fresh clone
therefore has no staging files: re-fetch with `src/acquire.py --restore` and
check against the manifest. That is a verified restore, not a re-pull. The
count series under `data/raw/counts/` are small and are committed outright.

**`governance/freeze.toml` is the authoritative protected-path list.** It grows
by phase: the raw manifest and count series first, the conformed CSVs when the
governed model is built, the page when it is rendered. Each addition is its own
commit. Nothing numeric is edited once frozen.

**Both gates must pass before anything is committed under `data/conformed/`
or `docs/`**: `src/validate.py`, `src/validate_measures.py` and
`src/test_golden.py` (the module's own checks) and `src/validate_freeze.py`.
Any of them exiting non-zero means publish nothing, commit nothing.

## The interpreter

**Name it by full path, never bare `python`.** The project venv is
`.venv/Scripts/python.exe`, created from
`C:\Users\Ajayr\AppData\Local\Python\pythoncore-3.14-64\python.exe` with
`--system-site-packages` so it inherits DuckDB, pandas, numpy, requests and
Playwright, and adds `statsmodels` pinned in `requirements.txt`. Bare `python`
on this machine is `C:\Python314\python.exe`, an empty 3.14.7: a script that
imports duckdb dies under it. `run.ps1` names the venv interpreter by path on
every line. The git hooks resolve `python3`, `python`, `py` in that order and
need only the standard library.

## Committing

**Stage by name - never the two blanket forms.** They are denied in
`.claude/settings.json`, and that block does **not** bind under
`bypassPermissions`. What binds is
`.claude/hooks/no_blanket_add_or_force_push.py`, a `PreToolUse` hook.

**Line-ending churn on frozen data is not cosmetic** - it makes "the snapshot
is untouched" unassertable. `.gitattributes` prevents it; the git `pre-commit`
hook in `.githooks/` catches what gets through and refuses the commit, and it
fails closed. **It is inert until `git config core.hooksPath .githooks` has
been run in this clone**, and on POSIX it is also inert unless
`.githooks/pre-commit` is tracked `100755`; confirm with
`git ls-files -s .githooks/pre-commit`. Run
`python .claude/hooks/hook_test_matrix.py` to confirm the guards behave.

**This repo's root commit was made from a session rooted at `C:\Projects`,
deliberately.** Hooks load only from the primary working directory, so the
session that installed the guard layer was not governed by it; the session
then changed its working directory here, and everything after the root commit
was done under the guard. The hook-manifest entry in
`cascadia-standards/governance/hook_manifest.json` is owed to a session rooted
there and is not written from here.

**A stale `.git/index.lock` is benign** - delete it and retry.
`git update-index --refresh` reveals one; `git status` does not.

## Publishing

Held. No remote, no push, no Pages, no site surfacing and no merge to `main`
until Aaron does each one himself. `git push` is in the `ask` list and stays
there. When it is published, `docs/` is served by GitHub Pages from `main`.

## The live edge

**A weekly scheduled task, from the Code store, reports and never publishes.**
Its file is `C:\Users\Ajayr\.claude\scheduled-tasks\cascadia-early-warning-live-edge\SKILL.md`
(the Code store, which `C:\Users\Ajayr\Claude\Scheduled\` is not; the two
stores do not see each other). It runs `src/pull_live_edge.py` then
`src/reconcile_live_edge.py` with the venv interpreter by path, writes
`data/live/`, `governance/run_history.jsonl`, `governance/health.json` and
`governance/reconciliation.md`, and rebuilds `docs/index.html` as its last
step. Live months are raw counts with no exclusion applied and say so (D18).
Committing a run's record is Aaron's act; `.claude/hooks/no_publish_from_scheduled_runs.py`
refuses a commit or a push from a scheduled transcript, and a push from any
transcript it cannot read. The rebuilt page trips the freeze gate until the
baseline in `governance/freeze.toml` is advanced with that commit (D18).
`src/test_live_edge.py` drives the pull offline against a fake source.

## Content

**Canonical domain is `https://www.robbinsanalytics.com`.** Every absolute URL
uses it.

**Page chrome follows the Felix design system, by pointer, not copy.** The
file is `C:\Projects\cascadia-standards\design-system\felix-design-system.md`
at the commit recorded in `governance/decision-record.md` (D-Felix). It is
never copied into this repo, and no token or class string is changed beyond
the one contrast rule recorded there. Charts follow VIZ-PRINCIPLES v2.8 gated
by CHART-REVIEW v2.8 (D-Viz); inside a chart canvas VIZ-PRINCIPLES wins over
Felix. The four Felix font families load from Google Fonts at runtime, which
no other module page does; that is a recorded collision, not an oversight.

**Generated, not authored:** `data/raw/manifest.json`, everything under
`data/raw/counts/` and `data/conformed/`, `governance/validation_report.md`,
`governance/reconciliation.md`, `governance/health.json`, `docs/index.html`,
`docs/case-study.html` and `docs/renders/`. Regenerate with the scripts in
`src/`; hand-editing any of them is a recurring failure mode elsewhere in this
estate. The two templates, `docs/template.html` and
`docs/case-study-template.html`, are authored; `src/build_page.py` writes both
pages in one run, so the live edge's weekly rebuild rewrites both.

**No em dashes in anything rendered under `docs/`.** The names gate and the
em-dash gate in `src/validate.py` run over `docs/` and the committed files
they name.

**Two page facts the next session will meet.** The page `<title>` joins its
two parts with a hyphen where Felix shows an em dash: the em-dash gate runs
over everything under `docs/` and the gate wins (D14 amendment). The desktop
app's preview tool wants a `.claude/launch.json` at `C:\Projects`, outside
this repository; `src/render_charts.py` expects the page at
`http://localhost:8731/`, which `python -m http.server 8731 --directory docs`
provides (the repo's own `.claude/launch.json` names the same command).

**The chart review is a record, not a form.** `governance/chart-review.md`
carries the Rule 7.4 panel (roster, verbatim returns, disposition, D/N/R),
the per-chart checklist and the author's own findings; a revision gets the
gate and a link, not a new panel. `governance/pre-panel-notes.md` is written
before any seat is spawned and never after.
