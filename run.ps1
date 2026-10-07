# run.ps1 -- the one entry point. Names the interpreter by path on every line.
#
#   .\run.ps1 acquire    re-pull the source: counts, extract, bulk, vmsr, register.
#                        A DELIBERATE REFRESH. Overwrites the freeze. Never a
#                        side effect of anything else here.
#   .\run.ps1 validate   every gate, offline: golden, measures, validate
#                        (with the proof the checks can fail), freeze.
#   .\run.ps1 build      conform, forecast, score, review, recall context,
#                        page. Offline. No network request is made.
#   .\run.ps1 all        validate, then build, then validate again.
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

function Step($label, $args) {
    Write-Host "== $label"
    & $Py @args
    if ($LASTEXITCODE -ne 0) { Write-Error "$label exited $LASTEXITCODE"; exit $LASTEXITCODE }
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
        Step "build_model"     @("src/build_model.py")
        Step "forecast"        @("src/forecast.py")
        Step "score"           @("src/score.py")
        Step "review"          @("src/review.py")
        Step "recall_context"  @("src/recall_context.py")
        Step "build_page"      @("src/build_page.py")
    }
    "all" {
        & $PSCommandPath validate
        & $PSCommandPath build
        & $PSCommandPath validate
    }
    default { Write-Error "unknown task '$Task'; one of acquire, validate, build, all" }
}
