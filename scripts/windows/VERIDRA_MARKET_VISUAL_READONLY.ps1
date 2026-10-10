# Run browser acceptance over saved Market Studies without opening the live app or writing data.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$dataRoot = Join-Path $env:LOCALAPPDATA 'Veridra\data\tenants'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Project venv missing: $python" }
if (-not (Test-Path -LiteralPath (Join-Path $dataRoot '_market_studies') -PathType Container)) {
    throw "Saved Market Studies not found at $dataRoot"
}
Push-Location $root
try {
    $env:VERIDRA_TENANT_DATA_ROOT = $dataRoot
    & $python tools/market_operator_readonly_visual.py
    if ($LASTEXITCODE -ne 0) { throw "Market Study browser acceptance failed ($LASTEXITCODE)" }
} finally { Pop-Location }
