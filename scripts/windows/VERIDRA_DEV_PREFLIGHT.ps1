# VERIDRA developer preflight: same core gates as CI verify, no app-data writes.
param(
    [switch]$Full,
    [switch]$BrowserAcceptance
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))
$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Missing .venv Python; run VERIDRA_SETUP.bat first." }
function Invoke-Gate([string]$label, [string[]]$arguments) {
    Write-Host ("[PREFLIGHT] " + $label) -ForegroundColor Cyan
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "$label failed (exit $LASTEXITCODE)" }
}
Invoke-Gate "Python compile" @("-m", "compileall", "-q", "src", "tests", "tools")
Invoke-Gate "Operator import audit" @("tools/audit_operator_imports.py")
Invoke-Gate "Ruff" @("-m", "ruff", "check", ".")
Invoke-Gate "Strict mypy" @("-m", "mypy", "src", "tests")
if ($Full) {
    Invoke-Gate "Full pytest" @("-m", "pytest", "-q", "--no-cov")
    Invoke-Gate "Deterministic audit" @("-m", "veridra.audit")
} else {
    Invoke-Gate "Focused pytest" @(
        "-m", "pytest", "-q", "--no-cov",
        "tests/test_webify_engagement_review.py",
        "tests/test_live_audit_review_acceptance.py",
        "tests/test_independent_backup_copy.py",
        "tests/test_recovery_readiness.py"
    )
}
if ($BrowserAcceptance) {
    Invoke-Gate "Prospect discovery browser acceptance" @(
        "scripts/browser/discovery_workflow_acceptance.py"
    )
}
Write-Host "[PREFLIGHT] ALL SELECTED GATES PASSED" -ForegroundColor Green
