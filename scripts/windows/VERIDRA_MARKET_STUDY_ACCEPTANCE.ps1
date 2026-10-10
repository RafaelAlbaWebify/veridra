# Safe, synthetic Market Study acceptance. Run from VERIDRA repository root.
# Uses pytest temp directories and mocked network calls; does not edit live market data.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$tests = @(
    'tests/test_market_intelligence.py',
    'tests/test_agency_market_study.py',
    'tests/test_market_selection_browser.py',
    'tests/test_market_website_audit_route.py',
    'tests/test_agency_market_map_browser.py',
    'tests/test_agency_market_map_http.py'
)
& python -m pytest @tests
if ($LASTEXITCODE -ne 0) {
    Write-Error "Synthetic Market Study Windows acceptance failed ($LASTEXITCODE)."
    exit $LASTEXITCODE
}
Write-Host 'Synthetic Market Study acceptance PASSED.'
Write-Host 'Real workstation reboot, real-site access and persistence require separate operator verification.'
