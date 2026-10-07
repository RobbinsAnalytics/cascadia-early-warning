# run.ps1 -- the one entry point. Names the interpreter by path on every line.
#
#   run.ps1 acquire    re-pull the source: counts, extract, bulk, vmsr, register.
#                      A DELIBERATE REFRESH. Overwrites the freeze. Never a
#                      side effect of anything else here.
#   run.ps1 validate   every gate, offline: golden, measures, validate
#                      (with the proof the checks can fail), freeze.
#   run.ps1 build      the pages, from the retained frozen outputs. Offline.
#                      Writes docs/ only; no stage that writes a frozen path.
#                      Needs the gitignored record table
#                      data/conformed/early_warning.duckdb (README, Rebuild).
#   run.ps1 all        validate, then build, then validate again; stops at the
#                      first failure with that stage's exit code.
#
# The execution policy on this machine is Restricted, so `.\run.ps1` is refused
# in a fresh shell. The working form, process-scoped and persisting nothing:
#
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 <task>
#
# WHAT `build` DOES NOT RUN, AND WHY. build_model.py, forecast.py, score.py,
# review.py and recall_context.py each write tables on governance/freeze.toml's
# protected list; forecast.py's locked stage refuses to run twice. Re-running
# them would rewrite the freeze, so `build` rebuilds only what is computed FROM
# the freeze: the page(s). The build session ran each of them directly, and
# the git log records what each one wrote. A reproduction task that re-runs
# them into a temporary copy and compares is a build-forward candidate.
#
# Bare `python` on this machine is an empty 3.14.7 (CLAUDE.md). This file never
# says `python`.

param([string]$Task = "build")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "no venv at $Py. Create it from C:\Users\Ajayr\AppData\Local\Python\pythoncore-3.14-64\python.exe with --system-site-packages, then pip install -r requirements.txt"
}
Set-Location $Root

# Never name a parameter $args: inside the body that name is PowerShell's
# automatic variable, which is empty, and python would start with no script
# at all and open its REPL (the defect this signature repairs).
function Step([string]$Label, [string[]]$StepArgs) {
    Write-Host "== $Label :: python $($StepArgs -join ' ')"
    & $Py @StepArgs
    $code = $LASTEXITCODE
    # Write-Error would throw under Stop before the exit ran, and the wrapper
    # would always exit 1; the stage's own code is what the caller gets.
    if ($code -ne 0) { [Console]::Error.WriteLine("$Label exited $code"); exit $code }
}

switch ($Task) {
    "acquire" {
        Step "acquire counts"   @("src/acquire.py", "counts")
        Step "acquire extract"  @("src/acquire.py", "extract")
        Step "acquire bulk"     @("src/acquire.py", "bulk")
        Step "acquire vmsr"     @("src/acquire.py", "vmsr")
        Step "acquire register" @("src/acquire.py", "register")
    }
    "validate" {
        Step "golden"            @("src/test_golden.py")
        Step "validate_measures" @("src/validate_measures.py")
        Step "validate"          @("src/validate.py", "--prove-failable")
        Step "validate_freeze"   @("src/validate_freeze.py")
    }
    "build" {
        Step "build_page"      @("src/build_page.py")
    }
    "all" {
        foreach ($t in @("validate", "build", "validate")) {
            & $PSCommandPath $t
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }
    default { Write-Error "unknown task '$Task'; one of acquire, validate, build, all" }
}
