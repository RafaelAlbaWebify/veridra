param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('start','open','stop','restart','status','preflight','backup','recovery-test','data-audit')]
    [string]$Command,
    [ValidateRange(1,65535)]
    [int]$Port = 8011,
    [string]$BackupPath
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateRoot = Join-Path $env:LOCALAPPDATA 'VeridraCommercial'
$DataRoot = Join-Path $StateRoot 'data'
$RuntimeRoot = Join-Path $StateRoot 'runtime'
$BackupRoot = Join-Path $StateRoot 'backups'
$ConfigRoot = Join-Path $StateRoot 'config'
$PythonExe = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Url = "http://127.0.0.1:$Port/"
$PidFile = Join-Path $RuntimeRoot 'veridra-commercial.pid'
$MonitoringPidFile = Join-Path $RuntimeRoot 'veridra-commercial-monitoring.pid'
$CrawlPidFile = Join-Path $RuntimeRoot 'veridra-commercial-crawl.pid'
$StdoutLogFile = Join-Path $RuntimeRoot 'veridra-commercial.stdout.log'
$StderrLogFile = Join-Path $RuntimeRoot 'veridra-commercial.stderr.log'
$MonitoringStdoutLogFile = Join-Path $RuntimeRoot 'veridra-commercial-monitoring.stdout.log'
$MonitoringStderrLogFile = Join-Path $RuntimeRoot 'veridra-commercial-monitoring.stderr.log'
$CrawlStdoutLogFile = Join-Path $RuntimeRoot 'veridra-commercial-crawl.stdout.log'
$CrawlStderrLogFile = Join-Path $RuntimeRoot 'veridra-commercial-crawl.stderr.log'

function Write-Step([string]$Message) { Write-Host "[Veridra Commercial] $Message" }

function Ensure-Directories {
    foreach ($path in @($StateRoot,$DataRoot,$RuntimeRoot,$BackupRoot,$ConfigRoot)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }
}

function Ensure-Python {
    if (Test-Path $PythonExe) { return }
    Write-Step 'Local virtual environment is missing; running standard VERIDRA setup...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'veridra-local.ps1') setup
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $PythonExe)) {
        throw 'VERIDRA setup did not create the expected Python environment.'
    }
}

function Set-BaseCommercialEnvironment {
    $env:VERIDRA_ENV = 'local'
    $env:VERIDRA_BIND_HOST = '127.0.0.1'
    $env:VERIDRA_BIND_PORT = "$Port"
    $env:VERIDRA_ALLOWED_HOSTS = '127.0.0.1,localhost'
    $env:VERIDRA_TRUSTED_ORIGIN = $Url.TrimEnd('/')
    $env:VERIDRA_IDENTITY_DB = Join-Path $DataRoot 'identity\veridra.sqlite3'
    $env:VERIDRA_TENANT_DATA_ROOT = Join-Path $DataRoot 'tenants'
}

function Set-CommercialEnvironment {
    Set-BaseCommercialEnvironment
    Remove-Item Env:VERIDRA_LOCAL_AGENCY -ErrorAction SilentlyContinue
    $env:VERIDRA_BROWSER_PROFILE_DIRECTORY = Join-Path $StateRoot 'browser-profile'
    Remove-Item Env:VERIDRA_LOCAL_AUTOLOGIN -ErrorAction SilentlyContinue
}

function Get-ManagedProcess(
    [string]$Path,
    [string]$ExpectedCommandLineFragment = ''
) {
    if (-not (Test-Path $Path)) { return $null }
    $pidText = (Get-Content $Path -Raw).Trim()
    if ($pidText -notmatch '^\d+$') {
        Remove-Item $Path -Force -ErrorAction SilentlyContinue
        return $null
    }
    $processId = [int]$pidText
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item $Path -Force -ErrorAction SilentlyContinue
        return $null
    }
    if ($ExpectedCommandLineFragment) {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        $commandLine = if ($cim) { [string]$cim.CommandLine } else { '' }
        if (-not $commandLine -or $commandLine -notlike "*$ExpectedCommandLineFragment*") {
            Remove-Item $Path -Force -ErrorAction SilentlyContinue
            return $null
        }
    }
    return $process
}

function Wait-Ready([int]$Seconds = 30) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $healthUrl = $Url.TrimEnd('/') + '/health/live'
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch {
            # The server may still be starting. Never treat 401 login as a health failure.
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Commercial VERIDRA did not become ready. Review $StderrLogFile"
}

function Start-Worker(
    [string]$Name,
    [string]$PidPath,
    [string[]]$Arguments,
    [string]$Stdout,
    [string]$Stderr
) {
    $expectedFragment = ($Arguments -join ' ')
    if (Get-ManagedProcess $PidPath $expectedFragment) { return }
    Write-Step "Starting $Name..."
    $process = Start-Process -FilePath $PythonExe -ArgumentList $Arguments -WorkingDirectory $RepoRoot -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -PassThru -WindowStyle Hidden
    Set-Content -Path $PidPath -Value $process.Id -Encoding ascii
    Start-Sleep -Milliseconds 500
    if (-not (Get-ManagedProcess $PidPath $expectedFragment)) {
        throw "$Name stopped unexpectedly. Review $Stderr"
    }
}

function Invoke-Start {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment

    if (-not (Get-ManagedProcess $PidFile '-m veridra.runtime')) {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($connection) { throw "Port $Port is already occupied by another process." }
        Write-Step "Starting local commercial web runtime at $Url"
        $process = Start-Process -FilePath $PythonExe -ArgumentList @('-m','veridra.runtime') -WorkingDirectory $RepoRoot -RedirectStandardOutput $StdoutLogFile -RedirectStandardError $StderrLogFile -PassThru -WindowStyle Hidden
        Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
        Wait-Ready
    }

    Start-Worker 'monitoring service' $MonitoringPidFile @('-m','veridra.monitoring_service','--interval','30') $MonitoringStdoutLogFile $MonitoringStderrLogFile
    Start-Worker 'crawl worker service' $CrawlPidFile @('-m','veridra.crawl_worker_service','--interval','10','--limit','5') $CrawlStdoutLogFile $CrawlStderrLogFile
    Wait-Ready
    Write-Step "Ready at $Url"
}

function Stop-One(
    [string]$Name,
    [string]$PidPath,
    [string]$ExpectedCommandLineFragment
) {
    $process = Get-ManagedProcess $PidPath $ExpectedCommandLineFragment
    if (-not $process) { return }
    Write-Step "Stopping $Name process $($process.Id)..."
    Stop-Process -Id $process.Id -Force
    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
}

function Invoke-Stop {
    Stop-One 'crawl worker' $CrawlPidFile '-m veridra.crawl_worker_service'
    Stop-One 'monitoring' $MonitoringPidFile '-m veridra.monitoring_service'
    Stop-One 'web' $PidFile '-m veridra.runtime'
    Write-Step 'Stopped.'
}

function Invoke-Status {
    $web = Get-ManagedProcess $PidFile '-m veridra.runtime'
    $monitoring = Get-ManagedProcess $MonitoringPidFile '-m veridra.monitoring_service'
    $crawl = Get-ManagedProcess $CrawlPidFile '-m veridra.crawl_worker_service'
    Write-Step ("Web: " + $(if ($web) { "running PID $($web.Id) at $Url" } else { 'stopped' }))
    Write-Step ("Monitoring: " + $(if ($monitoring) { "running PID $($monitoring.Id)" } else { 'stopped' }))
    Write-Step ("Crawl worker: " + $(if ($crawl) { "running PID $($crawl.Id)" } else { 'stopped' }))
    Write-Step 'Mode: Webify private local agency (no VERIDRA SaaS plan/billing gate)'
    if ($web -and $monitoring -and $crawl) { exit 0 }
    exit 1
}

function Invoke-Preflight {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    Write-Step 'Running Webify local-agency production preflight...'
    & $PythonExe -m veridra.production_preflight_cli
    $code = $LASTEXITCODE
    if ($code -eq 2) { throw 'Local commercial preflight has critical failures.' }
    if ($code -eq 1) {
        Write-Step 'Preflight passed with warnings; optional integrations remain unconfigured.'
    } else {
        Write-Step 'Preflight passed.'
    }
}

function Invoke-Backup {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    $identityDb = $env:VERIDRA_IDENTITY_DB
    $tenantRoot = $env:VERIDRA_TENANT_DATA_ROOT
    if (-not (Test-Path $identityDb)) { throw 'No commercial identity database exists yet.' }
    if (-not (Test-Path $tenantRoot)) { throw 'No commercial tenant data exists yet.' }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $target = Join-Path $BackupRoot "VERIDRA_COMMERCIAL_BACKUP_$stamp.zip"
    $wasRunning = [bool](
        (Get-ManagedProcess $PidFile '-m veridra.runtime') -or
        (Get-ManagedProcess $MonitoringPidFile '-m veridra.monitoring_service') -or
        (Get-ManagedProcess $CrawlPidFile '-m veridra.crawl_worker_service')
    )
    if ($wasRunning) { Invoke-Stop }
    try {
        & $PythonExe -m veridra.backup_restore_cli backup `
            --output $target `
            --identity-db $identityDb `
            --tenant-data-root $tenantRoot `
            --confirm-quiesced
        if ($LASTEXITCODE -ne 0) { throw 'Commercial backup failed.' }
        Write-Step "Verified backup created: $target"
    } finally {
        if ($wasRunning) { Invoke-Start }
    }
}

function Invoke-RecoveryTest {
    Ensure-Directories
    Ensure-Python
    $archive = if ($BackupPath) {
        (Resolve-Path $BackupPath).Path
    } else {
        $latest = Get-ChildItem $BackupRoot -Filter 'VERIDRA_COMMERCIAL_BACKUP_*.zip' |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if (-not $latest) { throw 'No verified commercial backup was found.' }
        $latest.FullName
    }
    $testRoot = Join-Path $StateRoot ("recovery-test-" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    $identityDb = Join-Path $testRoot 'identity\veridra.sqlite3'
    $tenantRoot = Join-Path $testRoot 'tenants'
    New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
    & $PythonExe -m veridra.backup_restore_cli restore `
        --archive $archive `
        --identity-db $identityDb `
        --tenant-data-root $tenantRoot `
        --confirm-quiesced
    if ($LASTEXITCODE -ne 0) { throw 'Commercial recovery test failed.' }
    & $PythonExe -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); r=c.execute('PRAGMA quick_check').fetchone()[0]; c.close(); print('sqlite_quick_check=' + str(r)); raise SystemExit(0 if r == 'ok' else 1)" $identityDb
    if ($LASTEXITCODE -ne 0) {
        throw 'Restored commercial identity database integrity check failed.'
    }
    Write-Step "Isolated commercial recovery PASS: $testRoot"
}


function Invoke-DataAudit {
    Ensure-Directories
    Ensure-Python
    $inventoryScript = Join-Path $RepoRoot 'tools\\webify_data_inventory.py'
    if (-not (Test-Path -LiteralPath $inventoryScript)) {
        throw 'Read-only Webify data inventory tool is missing.'
    }
    # Existing backup action briefly quiesces only managed VERIDRA processes,
    # and restarts them in its finally block. Do not use live database paths.
    Invoke-Backup
    $latest = Get-ChildItem -LiteralPath $BackupRoot -Filter 'VERIDRA_COMMERCIAL_BACKUP_*.zip' |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) { throw 'Verified backup was not found after backup.' }
    $previousTests = @(Get-ChildItem -LiteralPath $StateRoot -Directory -Filter 'recovery-test-*' |
        Select-Object -ExpandProperty FullName)
    Invoke-RecoveryTest
    $restores = @(Get-ChildItem -LiteralPath $StateRoot -Directory -Filter 'recovery-test-*' |
        Where-Object { $_.FullName -notin $previousTests } |
        Sort-Object LastWriteTime -Descending)
    if ($restores.Count -ne 1) {
        throw 'Cannot uniquely identify new isolated recovery-test directory.'
    }
    $restoredRoot = $restores[0].FullName
    $identityDb = Join-Path $restoredRoot 'identity\\veridra.sqlite3'
    $tenantRoot = Join-Path $restoredRoot 'tenants'
    $auditText = & $PythonExe $inventoryScript --identity-db $identityDb --tenant-root $tenantRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Read-only snapshot inventory rejected the restored database.'
    }
    $audit = $auditText | ConvertFrom-Json
    if ($audit.identity.state -ne 'readable' -or $audit.identity.integrity -ne 'ok') {
        throw 'Snapshot inventory did not confirm identity database integrity.'
    }
    $auditDir = Join-Path $StateRoot 'audits'
    New-Item -ItemType Directory -Force -Path $auditDir | Out-Null
    $auditPath = Join-Path $auditDir ("WEBIFY_DATA_AUDIT_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
    [System.IO.File]::WriteAllText($auditPath, ($audit | ConvertTo-Json -Depth 12))
    Write-Step "Read-only restored-snapshot inventory PASS: $auditPath"
    Write-Step 'Share the JSON summary only. Do not upload source databases or client files.'
}

switch ($Command) {
    'start' { Invoke-Start }
    'open' { Invoke-Start; Start-Process ($Url.TrimEnd('/') + '/agency') }
    'stop' { Invoke-Stop }
    'restart' { Invoke-Stop; Invoke-Start }
    'status' { Invoke-Status }
    'preflight' { Invoke-Preflight }
    'backup' { Invoke-Backup }
    'recovery-test' { Invoke-RecoveryTest }
    'data-audit' { Invoke-DataAudit }
}
