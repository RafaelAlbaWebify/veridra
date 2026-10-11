# Read-only browser check against a running VERIDRA operator server.
# Requires existing local auto-login; does not submit credentials or commercial forms.
param([ValidateRange(1,65535)][int]$Port = 8010)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Missing project virtual environment: $python" }
$root = Join-Path $env:LOCALAPPDATA 'Veridra\data\tenants\_market_studies'
if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'No saved Market Studies found.' }
$files = @(Get-ChildItem -LiteralPath $root -Recurse -Filter '*.json' -File)
if ($files.Count -ne 1) { throw "Expected exactly one saved Market Study, found $($files.Count)" }
$study = Get-Content -LiteralPath $files[0].FullName -Raw -Encoding utf8 | ConvertFrom-Json
$count = @($study.businesses).Count
if ($count -lt 1) { throw 'No saved business records.' }
Push-Location $repo
try {
    & $python tools/market_operator_live_readonly.py --base-url "http://127.0.0.1:$Port" --expected-count $count
    if ($LASTEXITCODE -ne 0) { throw "Authenticated browser smoke test failed ($LASTEXITCODE)" }
} finally { Pop-Location }
