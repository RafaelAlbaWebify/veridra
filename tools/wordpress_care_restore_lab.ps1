# Disposable isolated restore of the latest matching lab backup pair.
[CmdletBinding()]
param([string]$LabPath = "$HOME\Documents\WebifyLabs\wordpress-care")
$ErrorActionPreference = 'Stop'
$project = 'webify-wp-check-' + (Get-Date -Format HHmmss) + '-' + (Get-Random -Minimum 1000 -Maximum 9999)
$port = 18089
$compose = Join-Path $LabPath 'compose.yaml'
$backupDir = Join-Path $LabPath 'backups'
$tempCompose = Join-Path $LabPath ('compose.' + $project + '.yaml')
$created = @()
$report = [ordered]@{contract='wordpress_care_isolated_restore_v1';passed=$false;project=$project;checks=[ordered]@{}}
function Invoke-Docker([string[]]$Arguments) {
    $output = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('Docker failed: ' + ($output | Out-String)) }
    return $output
}
try {
    if (-not (Test-Path $compose)) { throw 'Lab Compose not found' }
    if ((Invoke-Docker @('context','show') | Out-String).Trim() -ne 'desktop-linux') { throw 'Unexpected Docker context' }
    $source = Get-Content $compose -Raw
    if (-not $source.Contains('127.0.0.1:8088:80')) { throw 'Incorrect lab Compose port' }
    $source.Replace('127.0.0.1:8088:80','127.0.0.1:18089:80') | Set-Content $tempCompose -Encoding utf8
    Invoke-Docker @('compose','-f',$tempCompose,'-p',$project,'config','--quiet') | Out-Null
    $pairs = @(Get-ChildItem $backupDir -Filter 'db_data-*.tar.gz' | Sort-Object LastWriteTimeUtc -Descending | ForEach-Object {
        $s = $_.Name.Substring(8,$_.Name.Length - 15)
        if (Test-Path (Join-Path $backupDir ('wp_data-' + $s + '.tar.gz'))) { $s }
    })
    if (-not $pairs.Count) { throw 'No matching backup pair found' }
    $stamp = $pairs[0]
    $report['stamp'] = $stamp
    foreach ($suffix in @('db_data','wp_data')) {
        $name = $project + '_' + $suffix
        & docker volume inspect $name *> $null
        if ($LASTEXITCODE -eq 0) { throw ('Refusing existing volume ' + $name) }
        Invoke-Docker @('volume','create',$name) | Out-Null
        $created += $name
        Invoke-Docker @('run','--rm','--mount',('type=volume,source=' + $name + ',target=/restore'),'--mount',('type=bind,source=' + $backupDir + ',target=/backup,readonly'),'busybox:1.37','tar','-xzf',('/backup/' + $suffix + '-' + $stamp + '.tar.gz'),'-C','/restore') | Out-Null
    }
    $report.checks['archives_restored']='PASS'
    Invoke-Docker @('compose','-f',$tempCompose,'-p',$project,'up','-d') | Out-Null
    $php = 'require "/var/www/html/wp-load.php"; update_option("home","http://127.0.0.1:18089"); update_option("siteurl","http://127.0.0.1:18089"); global $wpdb; $p=$wpdb->get_row($wpdb->prepare("SELECT post_content,post_status FROM {$wpdb->posts} WHERE post_title=%s AND post_type=%s LIMIT 1","Webify Backup Recovery Test","post")); if (!$p || $p->post_status!=="publish" || strpos($p->post_content,"This content must survive a complete backup and restoration.")===false) exit(2); echo "RESTORE PASS";'
    $ready=$false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        $result = & docker exec ($project + '-wordpress-1') php -r $php 2>&1
        if ($LASTEXITCODE -eq 0 -and ($result | Out-String).Contains('RESTORE PASS')) { $ready=$true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'Recovered post was not verified' }
    $report.checks['restored_content']='PASS'
    foreach ($p in @(8088,18089)) {
        $r = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $p + '/') -SkipHttpErrorCheck -MaximumRedirection 0 -TimeoutSec 20
        if ($r.StatusCode -ne 200) { throw ('HTTP failed on ' + $p) }
    }
    $report.checks['original_and_restore_http']='PASS'
    $report.passed=$true
} catch {
    $report['error'] = $_.Exception.Message
} finally {
    if (Test-Path $tempCompose) {
        & docker compose -f $tempCompose -p $project down *> $null
    }
    $clean=$true
    foreach ($name in $created) {
        & docker volume rm $name *> $null
        if ($LASTEXITCODE -ne 0) { $clean=$false }
    }
    Remove-Item $tempCompose -ErrorAction SilentlyContinue
    $report.checks['cleanup'] = if ($clean) {'PASS'} else {'FAIL'}
    if (-not $clean) { $report.passed=$false }
    $outputDir = Join-Path $LabPath 'acceptance\care-restore'
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    $path = Join-Path $outputDir ('restore-' + (Get-Date -Format yyyyMMddHHmmss) + '.json')
    $report | ConvertTo-Json -Depth 6 | Set-Content $path -Encoding utf8
    Write-Host ($report | ConvertTo-Json -Depth 6)
    Write-Host ('Evidence: ' + $path)
}
if (-not $report.passed) { throw 'ISOLATED RESTORE: FAIL' }
Write-Host 'ISOLATED RESTORE: PASS'
