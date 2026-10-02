param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('start','open','stop','restart','status','preflight','backup','recovery-test')]
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
    foreach ($path in @($StateRoot,$DataRoot,$RuntimeRoot,$BackupRoot)) {
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

function Set-CommercialEnvironment {
    $env:VERIDRA_ENV = 'production'
    $env:VERIDRA_BIND_HOST = '127.0.0.1'
    $env:VERIDRA_BIND_PORT = "$Port"
    $env:VERIDRA_ALLOWED_HOSTS = '127.0.0.1,localhost'
    $env:VERIDRA_TRUSTED_ORIGIN = $Url.TrimEnd('/')
    $env:VERIDRA_IDENTITY_DB = Join-Path $DataRoot 'identity\veridra.sqlite3'
    $env:VERIDRA_TENANT_DATA_ROOT = Join-Path $DataRoot 'tenants'
}

function Get-ManagedProcess([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    $pidText = (Get-Content $Path -Raw).Trim()
    if ($pidText -notmatch '^\d+$') {
        Remove-Item $Path -Force -ErrorAction SilentlyContinue
        return $null
    }
    $process = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item $Path -Force -ErrorAction SilentlyContinue
        return $null
    }
    return $process
}

function Wait-Ready([int]$Seconds = 30) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return }
        } catch {
            Start-Sleep -Milliseconds 500
        }
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
    if (Get-ManagedProcess $PidPath) { return }
    Write-Step "Starting $Name..."
    $process = Start-Process -FilePath $PythonExe -ArgumentList $Arguments -WorkingDirectory $RepoRoot -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -PassThru -WindowStyle Hidden
    Set-Content -Path $PidPath -Value $process.Id -Encoding ascii
    Start-Sleep -Milliseconds 500
    if (-not (Get-ManagedProcess $PidPath)) {
        throw "$Name stopped unexpectedly. Review $Stderr"
    }
}

function Invoke-Start {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment

    if (-not (Get-ManagedProcess $PidFile)) {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($connection) { throw "Port $Port is already occupied by another process." }
        Write-Step "Starting local commercial web runtime at $Url"
        $process = Start-Process -FilePath $PythonExe -ArgumentList @('-m','veridra.runtime') -WorkingDirectory $RepoRoot -RedirectStandardOutput $StdoutLogFile -RedirectStandardError $StderrLogFile -PassThru -WindowStyle Hidden
        Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
        Wait-Ready
    }

    Start-Worker 'monitoring service' $MonitoringPidFile @('-m','veridra.monitoring_service','--interval','30') $MonitoringStdoutLogFile $MonitoringStderrLogFile
    Start-Worker 'crawl worker service' $CrawlPidFile @('-m','veridra.crawl_worker_service','--interval','10','--limit','5') $CrawlStdoutLogFile $CrawlStderrLogFile
    Write-Step "Ready at $Url"
}

function Stop-One([string]$Name,[string]$PidPath) {
    $process = Get-ManagedProcess $PidPath
    if (-not $process) { return }
    Write-Step "Stopping $Name process $($process.Id)..."
    Stop-Process -Id $process.Id -Force
    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
}

function Invoke-Stop {
    Stop-One 'crawl worker' $CrawlPidFile
    Stop-One 'monitoring' $MonitoringPidFile
    Stop-One 'web' $PidFile
    Write-Step 'Stopped.'
}

function Invoke-Status {
    $web = Get-ManagedProcess $PidFile
    $monitoring = Get-ManagedProcess $MonitoringPidFile
    $crawl = Get-ManagedProcess $CrawlPidFile
    Write-Step ("Web: " + $(if ($web) { "running PID $($web.Id) at $Url" } else { 'stopped' }))
    Write-Step ("Monitoring: " + $(if ($monitoring) { "running PID $($monitoring.Id)" } else { 'stopped' }))
    Write-Step ("Crawl worker: " + $(if ($crawl) { "running PID $($crawl.Id)" } else { 'stopped' }))
    if ($web -and $monitoring -and $crawl) { exit 0 }
    exit 1
}

function Invoke-Preflight {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    Write-Step 'Running local commercial production preflight...'
    & $PythonExe -m veridra.production_preflight_cli
    $code = $LASTEXITCODE
    if ($code -eq 2) { throw 'Local commercial preflight has critical failures.' }
    if ($code -eq 1) {
        Write-Step 'Preflight passed with warnings; optional/public-provider items remain unconfigured.'
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
    $wasRunning = [bool]((Get-ManagedProcess $PidFile) -or (Get-ManagedProcess $MonitoringPidFile) -or (Get-ManagedProcess $CrawlPidFile))
    if ($wasRunning) { Invoke-Stop }
    try {
        & $PythonExe -m veridra.backup_restore_cli backup --output $target --identity-db $identityDb --tenant-data-root $tenantRoot --confirm-quiesced
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
        $latest = Get-ChildItem $BackupRoot -Filter 'VERIDRA_COMMERCIAL_BACKUP_*.zip' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $latest) { throw 'No verified commercial backup was found.' }
        $latest.FullName
    }
    $testRoot = Join-Path $StateRoot ("recovery-test-" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    $identityDb = Join-Path $testRoot 'identity\veridra.sqlite3'
    $tenantRoot = Join-Path $testRoot 'tenants'
    New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
    & $PythonExe -m veridra.backup_restore_cli restore --archive $archive --identity-db $identityDb --tenant-data-root $tenantRoot --confirm-quiesced
    if ($LASTEXITCODE -ne 0) { throw 'Commercial recovery test failed.' }
    & $PythonExe -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); r=c.execute('PRAGMA quick_check').fetchone()[0]; c.close(); print('sqlite_quick_check=' + str(r)); raise SystemExit(0 if r == 'ok' else 1)" $identityDb
    if ($LASTEXITCODE -ne 0) { throw 'Restored commercial identity database integrity check failed.' }
    Write-Step "Isolated commercial recovery PASS: $testRoot"
}

switch ($Command) {
    'start' { Invoke-Start }
    'open' { Invoke-Start; Start-Process ($Url.TrimEnd('/') + '/signup') }
    'stop' { Invoke-Stop }
    'restart' { Invoke-Stop; Invoke-Start }
    'status' { Invoke-Status }
    'preflight' { Invoke-Preflight }
    'backup' { Invoke-Backup }
    'recovery-test' { Invoke-RecoveryTest }
}
