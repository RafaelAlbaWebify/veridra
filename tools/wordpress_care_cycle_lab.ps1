# WordPress Care: single lab-only inspection -> backup -> isolated restore cycle.
[CmdletBinding()]
param([string]$LabPath = "$HOME\Documents\WebifyLabs\wordpress-care")
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSCommandPath
$backupScript = Join-Path $root 'wordpress_care_lab.ps1'
$restoreScript = Join-Path $root 'wordpress_care_restore_lab.ps1'
foreach ($file in @($backupScript,$restoreScript)) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing sibling script: $file" }
}
$report = [ordered]@{
  contract = 'webify_wordpress_care_cycle_v1'
  started_utc = [DateTimeOffset]::UtcNow.ToString('o')
  laboratory_only = $true
  steps = [ordered]@{inspect='NOT_RUN';backup='NOT_RUN';isolated_restore='NOT_RUN'}
  passed = $false
}
$resultsDir = Join-Path $LabPath 'acceptance\care-cycle'
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
$reportFile = Join-Path $resultsDir ('cycle-' + (Get-Date -Format 'yyyyMMddHHmmssfff') + '.json')
try {
    # Each child has its own JSON artifact. Redirect no output: visible full evidence.
    foreach ($action in @('inspect','backup')) {
        & $backupScript -LabPath $LabPath -Action $action
        if (-not $?) { throw "LAB $action failed" }
        $report.steps[$action] = 'PASS'
    }
    & $restoreScript -LabPath $LabPath
    if (-not $?) { throw 'Isolated restore failed' }
    $report.steps['isolated_restore']='PASS'
    $report.passed=$true
} catch {
    $report['error']=$_.Exception.Message
} finally {
    $report['finished_utc']=[DateTimeOffset]::UtcNow.ToString('o')
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportFile -Encoding utf8
    Write-Host ('CYCLE EVIDENCE: ' + $reportFile)
    Write-Host ($report | ConvertTo-Json -Depth 8)
}
if (-not $report.passed) { throw 'WORDPRESS CARE LAB CYCLE: FAIL' }
Write-Host 'WORDPRESS CARE LAB CYCLE: PASS'
