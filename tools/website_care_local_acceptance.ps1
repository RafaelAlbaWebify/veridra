# Safe import of existing WordPress Care cycle evidence into a separate local ledger.
# Run from repository root, with installed veridra Python package.
[CmdletBinding()]
param(
    [string]$LabPath = "$HOME\Documents\WebifyLabs\wordpress-care",
    [string]$WebsiteRef = "lab-wordpress-8088"
)
$ErrorActionPreference = 'Stop'
if ($WebsiteRef -ne 'lab-wordpress-8088') { throw 'Only the laboratory reference is accepted.' }
$evidenceDir = Join-Path $LabPath 'acceptance\care-cycle'
if (-not (Test-Path $evidenceDir)) { throw 'WordPress Care evidence directory missing.' }
$files = @(Get-ChildItem -LiteralPath $evidenceDir -Filter 'cycle-*.json' -File | Sort-Object LastWriteTimeUtc -Descending)
if (-not $files.Count) { throw 'No existing WordPress Care cycle evidence found.' }
$selected = $files[0].FullName
$ledger = Join-Path $LabPath 'acceptance\website-care-ledger.sqlite'
$env:VERIDRA_WEBSITE_CARE_DB = $ledger
Write-Host ('Evidence: ' + $selected)
Write-Host ('Ledger: ' + $ledger)
& python -m veridra.website_care_evidence $selected --db $ledger --website-ref $WebsiteRef --platform wordpress
if ($LASTEXITCODE -ne 0) { throw 'Import failed.' }
& python -m veridra.website_care_history --db $ledger --website-ref $WebsiteRef
if ($LASTEXITCODE -ne 0) { throw 'History verification failed.' }
Write-Host 'WEBSITE CARE LOCAL EVIDENCE ACCEPTANCE: PASS'
Write-Host 'To see the same ledger in VERIDRA, set VERIDRA_WEBSITE_CARE_DB to the printed absolute path before operator startup.'
