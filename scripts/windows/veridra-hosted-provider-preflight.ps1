$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "VERIDRA Python environment is missing at $Python"
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Output = Join-Path $HOME "Downloads\VERIDRA_HOSTED_PROVIDER_PREFLIGHT_$Stamp.json"

Push-Location $RepoRoot
try {
    & $Python -m veridra.hosted_provider_preflight --output $Output
    if ($LASTEXITCODE -ne 0) {
        throw "Hosted provider preflight failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "[Veridra] Hosted provider preflight passed."
Write-Host "[Veridra] Evidence: $Output"
