# Cascadia Early Warning - what an agent needs to know

A public-data module that forecasts the next month's volume of FDA medical
device reports for a small cohort of product codes, shows whether its forecasts
earned trust on a locked held-out period, and turns departures from
expectation into a human review queue. Source is openFDA `/device/event`,
`/device/recall`, `/device/enforcement` and `/device/classification`. It
publishes `docs/` to `https://www.robbinsanalytics.com/cascadia-early-warning/`
through GitHub Pages from `main` (see "Publishing": two lanes, D23).

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
The distinct report totals and the summary-report composition come from the
gitignored DuckDB record table when it is present, and must then equal the
committed `data/conformed/record_facts.json` or the build fails; without the
table (a fresh clone, the live-edge runner) they are read from that JSON. The
JSON is frozen and is written only by `src/build_page.py --write-record-facts`
(D23). Pages built either way are byte-identical.
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
Any of them exiting non-zero means publish nothing, commit nothing. The one
exception is the live-edge lane's own commit to the two pages. The runner
has no staging pages, DuckDB or private list, so it runs `test_golden.py`,
`validate_freeze.py` and the 19 `validate.py` checks that need none of
them, and not `validate_measures.py` (D23).

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

**Published.** The remote is `RobbinsAnalytics/cascadia-early-warning`
(public), and GitHub Pages serves `docs/` from `main`. Publication runs in
two lanes (PRINCIPLES v1.1.0 Principle 12; D23):

- **Build lane.** Anything that changes what a page claims or how it looks,
  and anything that governs the live-edge lane: both workflows under
  `.github/workflows/`, `governance/live-edge-allowlist.txt`, `src/`, the
  templates and `docs/assets/`, `requirements-live.txt`, `governance/freeze.toml`
  and every frozen path. Aaron reads it, then it ships. A session pushes,
  opens a PR or merges only when Aaron has said so for that change; `git push`
  is in the `ask` list and stays there.
- **Live-edge lane.** A scheduled or dispatched run of
  `.github/workflows/live-edge.yml` from `main`, changing only the paths on the
  allow-list. It publishes with no human step. Any failure after its push is
  build-lane work: the run does not revert itself.

**Nothing yet stops an unread change to a workflow or the allow-list from
reaching `main`** (no branch protection). That rests on the build lane being
followed.

## The live edge

**A GitHub Actions workflow publishes it: `.github/workflows/live-edge.yml`,
Tuesdays at 14:17 UTC** (07:17 Pacific in summer, 06:17 in winter), and by
manual dispatch from `main`. The dispatch has one input, `rehearse_failure`,
which stops the run after every gate and before the commit. Its logic lives
in `src/live_edge_lane.py`, so the YAML stays thin. `src/test_live_edge_lane.py`
tests that logic offline, and `.github/workflows/live-edge-check.yml` runs the
same checks read-only on every pull request to `main`.

**A run is two jobs.**

`build` has a read-only token. It:
1. reads `governance/live-edge-allowlist.txt` from the run's commit
   (`github.sha`), refusing globs and forbidden entries;
2. re-renders both pages and requires the committed bytes;
3. runs `src/pull_live_edge.py`, then `src/reconcile_live_edge.py`, which
   rebuilds both pages;
4. checks `outcome`: only `ok` or `skipped: source unchanged` publishes, so
   an outage or a rate limit fails loudly;
5. runs `test_live_edge.py`, the lane tests, `test_golden.py`,
   `validate_freeze.py` and the 19 `validate.py` checks a runner can run.
   The other six need the staging pages, the DuckDB or the private list, and
   `lane gates` names each one;
6. bundles the listed files it changed.

`publish` checks out `github.sha` afresh and runs only standard-library code
from that checkout. It:
1. applies the bundle;
2. re-checks `outcome`, the freeze gate and the path check;
3. stages by name and makes one commit as `github-actions[bot]`, with
   `.githooks` active;
4. range-checks the commit against `github.sha`;
5. pushes with a plain `git push origin HEAD:main`. Its push step is the
   only step with a write token;
6. requests a Pages build;
7. polls the public URLs until both pages serve the committed bytes.

**Every passing run commits its record, including a run that found nothing
new** ("skipped: source unchanged"). A failed pull exits non-zero, and nothing
is committed. The runner is ubuntu-24.04 with Python 3.14.6 and
`requirements-live.txt` (the full package closure, pinned by version and hash, binaries only). It
needs no DuckDB, because the page reads `data/conformed/record_facts.json`
(see "The freeze").

**What a run may change:** `data/live/`, `governance/run_history.jsonl`,
`governance/health.json`, `governance/reconciliation.md`, `docs/index.html`
and `docs/case-study.html`. Neither page is on the freeze gate's protected
list (D18), and the allow-list never names a template, `src/`, a workflow,
itself or a frozen path. Live months are raw counts with no exclusion
applied, and they say so (D18).

**SWITCH IT OFF in one action:** `gh workflow disable live-edge.yml`, or on
GitHub: Actions, Live edge, the "..." menu, Disable workflow. Turn it back on
with `gh workflow enable live-edge.yml`, or the same menu's Enable workflow.

**The Code-store scheduled task is retired** (D23). Its file,
`C:\Users\Ajayr\.claude\scheduled-tasks\cascadia-early-warning-live-edge\SKILL.md`,
now holds a RETIRED notice, and its schedule is disabled. That is the Code
store, which `C:\Users\Ajayr\Claude\Scheduled\` is not, and the two stores
do not see each other.

**A scheduled Claude session never commits, pushes or dispatches**
(SESSION-RULES 1a). `.claude/hooks/no_publish_from_scheduled_runs.py` is
unchanged. It refuses a commit or a push from a scheduled transcript, and a
push from any transcript it cannot read. It does not see a dispatch, so for a
dispatch that rule is the only guard. `src/test_live_edge.py` drives the pull
offline against a fake source.

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
