# Synthetic Market Study acceptance. Never touches the live operator data directory.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "VERIDRA project environment not found at $python. From repo root run: py -3.11 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e '.[dev]'"
}
Push-Location $repoRoot
try {
    & $python -c 'import veridra, pytest, playwright'
    if ($LASTEXITCODE -ne 0) {
        throw "VERIDRA test dependencies are missing in .venv. Run: .\.venv\Scripts\python.exe -m pip install -e '.[dev]'"
    }
    $tests = @(
        'tests/test_market_intelligence.py',
        'tests/test_agency_market_study.py',
        'tests/test_market_selection_browser.py',
        'tests/test_market_website_audit_route.py',
        'tests/test_agency_market_map_browser.py',
        'tests/test_agency_market_map_http.py'
    )
    & $python -m pytest @tests
    if ($LASTEXITCODE -ne 0) { throw "Synthetic Market Study Windows acceptance failed ($LASTEXITCODE)." }
    Write-Host 'Synthetic Market Study acceptance PASSED.'
    Write-Host 'Real workstation persistence and reboot still require separate verification.'
}
finally { Pop-Location }
