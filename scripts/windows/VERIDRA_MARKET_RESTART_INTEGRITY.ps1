# Read-only SHA256 integrity check for saved operator Market Studies.
# Capture before an operator restart; Verify after the app is restarted.
# Never writes to the VERIDRA data root. The manifest contains no business details.
param(
    [Parameter(Mandatory=$true)][ValidateSet('Capture','Verify')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$DataRoot,
    [string]$Manifest = (Join-Path $env:TEMP 'veridra-market-study-restart-baseline.json')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path -LiteralPath $DataRoot).Path
$studies = Join-Path $root '_market_studies'
if (-not (Test-Path -LiteralPath $studies -PathType Container)) {
    throw "No _market_studies folder under this data root. No evidence captured."
}
$files = @(Get-ChildItem -LiteralPath $studies -Filter '*.json' -Recurse -File)
if ($files.Count -eq 0) { throw 'No saved market studies found; refusing a false-positive PASS.' }
$records = @(
    foreach ($file in $files) {
        $data = Get-Content -LiteralPath $file.FullName -Raw -Encoding utf8 | ConvertFrom-Json
        if ($null -eq $data.study_id -or $null -eq $data.businesses) {
            throw "Invalid CityStudy structure in $($file.FullName)"
        }
        $relative = $file.FullName.Substring($studies.Length).TrimStart('\','/')
        $shortlistCount = if ($null -eq $data.shortlist) { 0 } else { @($data.shortlist.PSObject.Properties).Count }
        $qualificationCount = if ($null -eq $data.qualifications) { 0 } else { @($data.qualifications.PSObject.Properties).Count }
        $auditCount = if ($null -eq $data.website_audits) { 0 } else { @($data.website_audits.PSObject.Properties).Count }
        [pscustomobject]@{
            path = $relative
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
            businesses = @($data.businesses).Count
            shortlist = $shortlistCount
            qualifications = $qualificationCount
            website_audits = $auditCount
            crm_promoted = if ($null -eq $data.crm_promoted) { 0 } else { @($data.crm_promoted).Count }
        }
    }
) | Sort-Object path
$current = @($records)
Write-Host ("Saved studies: {0}; observed businesses: {1}" -f $current.Count, (($current | Measure-Object -Property businesses -Sum).Sum))
if ($Mode -eq 'Capture') {
    $Manifest = [System.IO.Path]::GetFullPath($Manifest)
    if ($Manifest.StartsWith($studies + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Baseline must be outside Market Study data.' }
    $manifestParent = Split-Path -Parent $Manifest
    if (-not (Test-Path -LiteralPath $manifestParent)) { New-Item -ItemType Directory -Path $manifestParent -Force | Out-Null }
    $payload = [pscustomobject]@{ schema_version = 1; studies = $current }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Manifest -Encoding utf8
    Write-Host "Baseline saved outside VERIDRA data: $Manifest"
    exit 0
}
if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) { throw 'Baseline missing. Run Capture before restart.' }
$baseline = Get-Content -LiteralPath $Manifest -Raw -Encoding utf8 | ConvertFrom-Json
if ($baseline.schema_version -ne 1) { throw 'Unsupported baseline format.' }
$before = @($baseline.studies | Sort-Object path | ConvertTo-Json -Depth 8)
$after = @($current | ConvertTo-Json -Depth 8)
if (($before -join '') -cne ($after -join '')) {
    Write-Error 'Market Study data changed between Capture and Verify. Inspect files before continuing.'
    exit 1
}
Write-Host 'PASS: saved Market Studies, hashes and decision counts unchanged after restart.'
