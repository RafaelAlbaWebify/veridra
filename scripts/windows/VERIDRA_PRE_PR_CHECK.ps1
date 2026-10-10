# Run from the VERIDRA repository root using its active Python environment.
# All three checks must pass BEFORE proposing a PR; CI remains the merge gate.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-QualityCheck {
    param([string]$Label, [string[]]$Arguments)
    Write-Host "=== $Label ==="
    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$Label failed (exit code $LASTEXITCODE). Stop: PR is not ready."
        exit $LASTEXITCODE
    }
}

Invoke-QualityCheck 'Ruff' @('-m', 'ruff', 'check', '.')
Invoke-QualityCheck 'Strict mypy' @('-m', 'mypy', 'src', 'tests')
Invoke-QualityCheck 'Pytest' @('-m', 'pytest')

Write-Host 'Local checks passed. CI and Windows acceptance still required before merge.'
