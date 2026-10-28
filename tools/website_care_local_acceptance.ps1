# Validate existing WordPress Care evidence using a self-contained, pinned importer.
# Does not install packages, checkout Git branches or touch VERIDRA customer data.
[CmdletBinding()]
param(
    [string]$LabPath = "$HOME\Documents\WebifyLabs\wordpress-care",
    [string]$WebsiteRef = "lab-wordpress-8088"
)
$ErrorActionPreference = 'Stop'
if ($WebsiteRef -ne 'lab-wordpress-8088') { throw 'Only the laboratory website reference is accepted.' }
$evidenceDir = Join-Path $LabPath 'acceptance\care-cycle'
if (-not (Test-Path $evidenceDir)) { throw 'WordPress Care evidence directory missing.' }
$files = @(Get-ChildItem -LiteralPath $evidenceDir -Filter 'cycle-*.json' -File |
    Sort-Object LastWriteTimeUtc -Descending)
if (-not $files.Count) { throw 'No existing WordPress Care cycle evidence found.' }
$selected = $files[0].FullName
$ledger = Join-Path $LabPath 'acceptance\website-care-ledger.sqlite'
$stage = Join-Path $env:TEMP 'webify-website-care-acceptance-modules'
$package = Join-Path $stage 'veridra'
New-Item -ItemType Directory -Path $package -Force | Out-Null
Set-Content -Path (Join-Path $package '__init__.py') -Value '' -Encoding utf8
# Both source modules are pinned to the merged PR #439 base revision.
# No pip installation and no local checkout mutation is necessary.
$revision = 'cf07c7daadf8edb8a8753aeab4ae0064863ed81b'
foreach ($module in @('website_care_evidence.py', 'website_care_history.py')) {
    $uri = "https://raw.githubusercontent.com/RafaelAlbaWebify/veridra/$revision/src/veridra/$module"
    Invoke-WebRequest -Uri $uri -OutFile (Join-Path $package $module)
}
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $stage
    Write-Host ('Evidence: ' + $selected)
    Write-Host ('Ledger: ' + $ledger)
    & python -m veridra.website_care_evidence $selected --db $ledger --website-ref $WebsiteRef --platform wordpress
    if ($LASTEXITCODE -ne 0) { throw 'Website Care import failed.' }
    & python -m veridra.website_care_history --db $ledger --website-ref $WebsiteRef
    if ($LASTEXITCODE -ne 0) { throw 'Website Care history verification failed.' }
    Write-Host 'WEBSITE CARE LOCAL EVIDENCE ACCEPTANCE: PASS'
    Write-Host 'VERIDRA_WEBSITE_CARE_DB should point to the ledger path above.'
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
