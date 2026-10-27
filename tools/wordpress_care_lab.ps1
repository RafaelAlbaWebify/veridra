# Webify WordPress Care — local laboratory maintenance (no customer targets)
# Run from PowerShell 7: pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\wordpress_care_lab.ps1
# Safe scope: ONLY the known Docker Compose laboratory project and its volumes.
[CmdletBinding()]
param(
    [ValidateSet('inspect','backup')]
    [string]$Action = 'inspect',
    [string]$LabPath = "$HOME\Documents\WebifyLabs\wordpress-care"
)
$ErrorActionPreference = 'Stop'
$project = 'webify-wp-lab'
$expectedServices = @('webify-wp-lab-db-1','webify-wp-lab-wordpress-1')
$port = 8088
$started = $false
$steps = [ordered]@{}
$report = [ordered]@{
    contract = 'webify_wordpress_care_lab_v1'
    action = $Action
    project = $project
    timestamp_utc = [DateTimeOffset]::UtcNow.ToString('o')
    checks = $steps
    passed = $false
}
function Invoke-Docker {
    param([string[]]$Arguments)
    $output = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "docker $($Arguments[0]) failed: $($output | Out-String)" }
    return $output
}
if (-not (Test-Path (Join-Path $LabPath 'compose.yaml'))) { throw 'Expected lab compose.yaml not found.' }
$actual = (Invoke-Docker @('context','show') | Out-String).Trim()
if ($actual -ne 'desktop-linux') { throw "Unexpected Docker context: $actual" }
$steps['docker_context'] = 'PASS'
$names = @(Invoke-Docker @('compose','-f',(Join-Path $LabPath 'compose.yaml'),'-p',$project,'ps','--format','json') | ForEach-Object { if ($_ -is [string] -and $_.Trim()) { ($_ | ConvertFrom-Json).Name } })
foreach ($name in $expectedServices) { if ($name -notin $names) { throw "Required laboratory service missing: $name" } }
$steps['lab_services'] = 'PASS'
$http = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -TimeoutSec 20 -MaximumRedirection 0 -SkipHttpErrorCheck
if ($http.StatusCode -ne 200) { throw "Lab HTTP status: $($http.StatusCode)" }
$steps['http_200'] = 'PASS'
# A PHP runtime check — no passwords, user details or document content in the report.
$php = 'require "/var/www/html/wp-load.php"; global $wpdb; echo json_encode(["version"=>get_bloginfo("version"),"database_ok"=>($wpdb->get_var("SELECT 1")=="1"),"plugin_updates"=>count(get_site_transient("update_plugins")->response ?? []),"theme_updates"=>count(get_site_transient("update_themes")->response ?? [])]);'
$raw = (Invoke-Docker @('exec','webify-wp-lab-wordpress-1','php','-r',$php) | Out-String).Trim()
$report['wordpress'] = $raw | ConvertFrom-Json
if (-not $report.wordpress.database_ok) { throw 'Database read check failed.' }
$steps['wordpress_database'] = 'PASS'
if ($Action -eq 'backup') {
    $backupDir = Join-Path $LabPath 'backups'
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $archives = @()
    # Stop DB and WordPress together for a consistent cold snapshot.
    try {
        Invoke-Docker @('compose','-f',(Join-Path $LabPath 'compose.yaml'),'-p',$project,'stop') | Out-Null
        $started = $true
        foreach ($suffix in @('db_data','wp_data')) {
            $name = "${project}_${suffix}"
            $vol = (Invoke-Docker @('volume','inspect',$name,'--format','{{.Name}}') | Out-String).Trim()
            if ($vol -ne $name) { throw 'Volume identity mismatch.' }
            $archive = "$suffix-$stamp.tar.gz"
            $dest = Join-Path $backupDir $archive
            if (Test-Path $dest) { throw "Refusing to overwrite: $dest" }
            Invoke-Docker @('run','--rm','--mount',"type=volume,source=$name,target=/source,readonly",'--mount',"type=bind,source=$backupDir,target=/backup",'busybox:1.37','tar','-czf',"/backup/$archive",'-C','/source','.') | Out-Null
            Invoke-Docker @('run','--rm','--mount',"type=bind,source=$backupDir,target=/backup,readonly",'busybox:1.37','tar','-tzf',"/backup/$archive") | Out-Null
            $archives += [ordered]@{ name=$archive; bytes=(Get-Item $dest).Length; sha256=(Get-FileHash $dest -Algorithm SHA256).Hash }
        }
        $report['archives'] = $archives
        $steps['cold_backup_integrity'] = 'PASS'
    }
    finally {
        if ($started) {
            Invoke-Docker @('compose','-f',(Join-Path $LabPath 'compose.yaml'),'-p',$project,'start') | Out-Null
        }
    }
    $steps['services_restarted'] = 'PASS'
}
$report.passed = $true
$outputDir = Join-Path $LabPath 'acceptance\care-maintenance'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$file = Join-Path $outputDir ("care-$([DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')).json")
$report | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $file -Encoding utf8
Write-Host ($report | ConvertTo-Json -Depth 7)
Write-Host "Evidence: $file"
Write-Host "WORDPRESS CARE LAB $($Action.ToUpperInvariant()): PASS"
