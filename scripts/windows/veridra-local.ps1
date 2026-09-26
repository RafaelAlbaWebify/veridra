param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('setup','start','operator-start','stop','restart','operator-restart','status','open','operator-open','operator-preflight','test','backup','restore','recovery-test','diagnostics','smtp-config','smtp-test','create-shortcut','remove-shortcut')]
    [string]$Command,
    [string]$BackupPath,
    [ValidateRange(1, 65535)]
    [int]$Port = 8010,
    [string]$SmtpHost,
    [ValidateRange(1, 65535)]
    [int]$SmtpPort = 587,
    [ValidateSet('starttls','implicit_tls')]
    [string]$SmtpEncryption = 'starttls',
    [string]$SmtpSender,
    [string]$SmtpSenderName = 'Veridra',
    [string]$SmtpUsername,
    [string]$SmtpTestRecipient,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateRoot = Join-Path $env:LOCALAPPDATA 'Veridra'
$DataRoot = Join-Path $StateRoot 'data'
$RuntimeRoot = Join-Path $StateRoot 'runtime'
$BackupRoot = Join-Path $StateRoot 'backups'
$ConfigRoot = Join-Path $StateRoot 'config'
$SmtpConfigFile = Join-Path $ConfigRoot 'smtp.json'
$SmtpSecretFile = Join-Path $ConfigRoot 'smtp-password.txt'
$VenvRoot = Join-Path $RepoRoot '.venv'
$PythonExe = Join-Path $VenvRoot 'Scripts\python.exe'
$PidFile = Join-Path $RuntimeRoot 'veridra.pid'
$MonitoringPidFile = Join-Path $RuntimeRoot 'veridra-monitoring.pid'
$StdoutLogFile = Join-Path $RuntimeRoot 'veridra.stdout.log'
$StderrLogFile = Join-Path $RuntimeRoot 'veridra.stderr.log'
$MonitoringStdoutLogFile = Join-Path $RuntimeRoot 'veridra-monitoring.stdout.log'
$MonitoringStderrLogFile = Join-Path $RuntimeRoot 'veridra-monitoring.stderr.log'
if ($env:VERIDRA_LOCAL_PORT) {
    $configuredPort = 0
    if (-not [int]::TryParse($env:VERIDRA_LOCAL_PORT, [ref]$configuredPort) -or $configuredPort -lt 1 -or $configuredPort -gt 65535) {
        throw 'VERIDRA_LOCAL_PORT must be an integer between 1 and 65535.'
    }
    $Port = $configuredPort
}
$Url = "http://127.0.0.1:$Port/"
$script:RuntimeProfile = 'development'

function Write-Step([string]$Message) { Write-Host "[Veridra] $Message" }
function Ensure-Directories {
    foreach ($path in @($StateRoot,$DataRoot,$RuntimeRoot,$BackupRoot,$ConfigRoot)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }
}
function Get-PythonCommand {
    foreach ($candidate in @('py','python')) {
        try {
            $version = & $candidate --version 2>&1
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { }
    }
    throw 'Python 3.11 or newer was not found. Install Python and enable the py launcher or PATH entry.'
}
function Assert-PythonVersion([string]$PythonCommand) {
    & $PythonCommand -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Veridra requires Python 3.11 or newer.' }
}
function Import-SmtpEnvironment {
    Remove-Item Env:VERIDRA_SMTP_HOST -ErrorAction SilentlyContinue
    Remove-Item Env:VERIDRA_SMTP_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:VERIDRA_SMTP_ENCRYPTION -ErrorAction SilentlyContinue
    Remove-Item Env:VERIDRA_SMTP_SENDER -ErrorAction SilentlyContinue
    Remove-Item Env:VERIDRA_SMTP_SENDER_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:VERIDRA_SMTP_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:VERIDRA_SMTP_PASSWORD -ErrorAction SilentlyContinue
    if (-not (Test-Path $SmtpConfigFile)) { return }
    $config = Get-Content $SmtpConfigFile -Raw | ConvertFrom-Json
    $env:VERIDRA_SMTP_HOST = [string]$config.host
    $env:VERIDRA_SMTP_PORT = [string]$config.port
    $env:VERIDRA_SMTP_ENCRYPTION = [string]$config.encryption
    $env:VERIDRA_SMTP_SENDER = [string]$config.sender
    $env:VERIDRA_SMTP_SENDER_NAME = [string]$config.sender_name
    if ($config.username) {
        $env:VERIDRA_SMTP_USERNAME = [string]$config.username
        if (-not (Test-Path $SmtpSecretFile)) { throw 'SMTP username is configured but the encrypted password file is missing.' }
        $secure = Get-Content $SmtpSecretFile -Raw | ConvertTo-SecureString
        $credential = New-Object System.Management.Automation.PSCredential('smtp', $secure)
        $env:VERIDRA_SMTP_PASSWORD = $credential.GetNetworkCredential().Password
    }
}
function Set-LocalEnvironment {
    $env:VERIDRA_ENV = $script:RuntimeProfile
    $env:VERIDRA_BIND_HOST = '127.0.0.1'
    $env:VERIDRA_BIND_PORT = "$Port"
    $env:VERIDRA_ALLOWED_HOSTS = '127.0.0.1,localhost'
    $env:VERIDRA_TRUSTED_ORIGIN = $Url.TrimEnd('/')
    $env:VERIDRA_IDENTITY_DB = Join-Path $DataRoot 'identity\veridra.sqlite3'
    $env:VERIDRA_TENANT_DATA_ROOT = Join-Path $DataRoot 'tenants'
    Import-SmtpEnvironment
}
function Get-ManagedProcess([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    $pidText = (Get-Content $Path -Raw).Trim()
    if ($pidText -notmatch '^\d+$') { Remove-Item $Path -Force; return $null }
    $process = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
    if (-not $process) { Remove-Item $Path -Force; return $null }
    return $process
}
function Get-VeridraProcess { return Get-ManagedProcess $PidFile }
function Get-MonitoringProcess { return Get-ManagedProcess $MonitoringPidFile }
function Wait-Ready([int]$Seconds = 30) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return }
        } catch { Start-Sleep -Milliseconds 500 }
    } while ((Get-Date) -lt $deadline)
    throw "Veridra did not become ready. Review $StdoutLogFile and $StderrLogFile"
}
function Invoke-Setup {
    Ensure-Directories
    $python = Get-PythonCommand
    Assert-PythonVersion $python
    if (-not (Test-Path $PythonExe)) {
        Write-Step 'Creating local virtual environment...'
        & $python -m venv $VenvRoot
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    Write-Step 'Installing Veridra and development dependencies...'
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -e "$RepoRoot[dev]"
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    Write-Step 'Installing Chromium used by browser and PDF workflows...'
    & $PythonExe -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
    Write-Step "Setup complete. Local data root: $DataRoot"
}
function Start-MonitoringService {
    if (Get-MonitoringProcess) { return }
    Set-LocalEnvironment
    Write-Step 'Starting recurring monitoring service...'
    $arguments = @('-m','veridra.monitoring_service','--interval','30')
    $process = Start-Process -FilePath $PythonExe -ArgumentList $arguments -WorkingDirectory $RepoRoot -RedirectStandardOutput $MonitoringStdoutLogFile -RedirectStandardError $MonitoringStderrLogFile -PassThru -WindowStyle Hidden
    Set-Content -Path $MonitoringPidFile -Value $process.Id -Encoding ascii
    Start-Sleep -Milliseconds 500
    if (-not (Get-MonitoringProcess)) { throw "Monitoring service stopped unexpectedly. Review $MonitoringStderrLogFile" }
}
function Invoke-Start {
    Ensure-Directories
    if (-not (Test-Path $PythonExe)) { Invoke-Setup }
    Set-LocalEnvironment
    $web = Get-VeridraProcess
    if (-not $web) {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($connection) { throw "Port $Port is already occupied by another process." }
        Write-Step "Starting local server on port $Port..."
        $arguments = @('-m','veridra.runtime')
        $process = Start-Process -FilePath $PythonExe -ArgumentList $arguments -WorkingDirectory $RepoRoot -RedirectStandardOutput $StdoutLogFile -RedirectStandardError $StderrLogFile -PassThru -WindowStyle Hidden
        Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
        Wait-Ready
    }
    Start-MonitoringService
    Write-Step "Ready at $Url"
}
function Stop-Managed([string]$Name, [string]$Path) {
    $process = Get-ManagedProcess $Path
    if (-not $process) { return }
    Write-Step "Stopping $Name process $($process.Id)..."
    Stop-Process -Id $process.Id -Force
    Remove-Item $Path -Force -ErrorAction SilentlyContinue
}
function Invoke-Stop {
    Stop-Managed 'monitoring' $MonitoringPidFile
    Stop-Managed 'web' $PidFile
    Write-Step 'Stopped.'
}
function Invoke-Status {
    $web = Get-VeridraProcess
    $monitoring = Get-MonitoringProcess
    Write-Step ("Web: " + $(if ($web) { "running PID $($web.Id) at $Url" } else { 'stopped' }))
    Write-Step ("Monitoring: " + $(if ($monitoring) { "running PID $($monitoring.Id)" } else { 'stopped' }))
    Write-Step ("SMTP: " + $(if (Test-Path $SmtpConfigFile) { 'configured' } else { 'not configured' }))
    if ($web -and $monitoring) { exit 0 }
    exit 1
}
function Invoke-OperatorStart {
    $script:RuntimeProfile = 'operator'
    Invoke-Start
}
function Invoke-OperatorRestart {
    $script:RuntimeProfile = 'operator'
    Invoke-Stop
    Invoke-Start
}
function Invoke-OperatorOpen {
    $script:RuntimeProfile = 'operator'
    Invoke-Start
    Start-Process $Url
}
function Invoke-OperatorPreflight {
    Ensure-Directories
    if (-not (Test-Path $PythonExe)) { Invoke-Setup }
    $script:RuntimeProfile = 'operator'
    Set-LocalEnvironment
    Write-Step 'Running hardened operator-local preflight...'
    & $PythonExe -m veridra.production_preflight_cli
    exit $LASTEXITCODE
}
function Invoke-Open { Invoke-Start; Start-Process $Url }
function Invoke-Test {
    if (-not (Test-Path $PythonExe)) { Invoke-Setup }
    Push-Location $RepoRoot
    try {
        & $PythonExe -m ruff check .
        if ($LASTEXITCODE -ne 0) { throw 'Ruff failed.' }
        & $PythonExe -m mypy src
        if ($LASTEXITCODE -ne 0) { throw 'mypy failed.' }
        & $PythonExe -m pytest
        if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }
    } finally { Pop-Location }
}
function Invoke-SmtpConfig {
    Ensure-Directories
    if (-not $SmtpHost) { $SmtpHost = Read-Host 'SMTP host' }
    if (-not $SmtpSender) { $SmtpSender = Read-Host 'Sender email' }
    if (-not $SmtpHost -or -not $SmtpSender) { throw 'SMTP host and sender email are required.' }
    $record = [ordered]@{
        host = $SmtpHost
        port = $SmtpPort
        encryption = $SmtpEncryption
        sender = $SmtpSender
        sender_name = $SmtpSenderName
        username = $SmtpUsername
    }
    $record | ConvertTo-Json | Set-Content -Path $SmtpConfigFile -Encoding utf8
    if ($SmtpUsername) {
        $secure = Read-Host 'SMTP password (stored encrypted for this Windows user)' -AsSecureString
        $secure | ConvertFrom-SecureString | Set-Content -Path $SmtpSecretFile -Encoding ascii
    } else {
        Remove-Item $SmtpSecretFile -Force -ErrorAction SilentlyContinue
    }
    Write-Step "SMTP configuration saved outside the repository: $SmtpConfigFile"
    Write-Step 'Restart Veridra to apply the new mail configuration.'
}
function Invoke-SmtpTest {
    Ensure-Directories
    if (-not (Test-Path $PythonExe)) { Invoke-Setup }
    $script:RuntimeProfile = 'operator'
    Set-LocalEnvironment
    if (-not (Test-Path $SmtpConfigFile)) { throw 'SMTP is not configured. Run VERIDRA_SMTP_CONFIG.bat first.' }
    if (-not $SmtpTestRecipient) { $SmtpTestRecipient = Read-Host 'SMTP test recipient email' }
    if (-not $SmtpTestRecipient) { throw 'SMTP test recipient is required.' }
    Write-Step "Sending SMTP verification message to $SmtpTestRecipient..."
    & $PythonExe -m veridra.smtp_check_cli --recipient $SmtpTestRecipient
    if ($LASTEXITCODE -ne 0) { throw 'SMTP verification failed.' }
    Write-Step 'SMTP verification PASS.'
}

function Invoke-Backup {
    Ensure-Directories
    if (-not (Test-Path $PythonExe)) { Invoke-Setup }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $target = Join-Path $BackupRoot "VERIDRA_BACKUP_$stamp.zip"
    $identityDb = Join-Path $DataRoot 'identity\veridra.sqlite3'
    $tenantRoot = Join-Path $DataRoot 'tenants'
    if (-not (Test-Path $identityDb)) { throw 'No local identity database exists.' }
    if (-not (Test-Path $tenantRoot)) { throw 'No local tenant data directory exists.' }

    $wasRunning = [bool]((Get-VeridraProcess) -or (Get-MonitoringProcess))
    if ($wasRunning) {
        Write-Step 'Pausing Veridra for a verified consistent backup...'
        Invoke-Stop
        Start-Sleep -Milliseconds 500
    }
    try {
        & $PythonExe -m veridra.backup_restore_cli backup `
            --output $target `
            --identity-db $identityDb `
            --tenant-data-root $tenantRoot `
            --confirm-quiesced
        if ($LASTEXITCODE -ne 0) { throw 'Verified backup creation failed.' }
        Write-Step "Verified backup created: $target"
    } finally {
        if ($wasRunning) {
            Write-Step 'Restarting Veridra after backup...'
            Invoke-Start
        }
    }
}

function Invoke-RecoveryTest {
    Ensure-Directories
    if (-not (Test-Path $PythonExe)) { Invoke-Setup }
    $archive = if ($BackupPath) {
        (Resolve-Path $BackupPath).Path
    } else {
        $latest = Get-ChildItem $BackupRoot -Filter 'VERIDRA_BACKUP_*.zip' |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if (-not $latest) { throw 'No verified Veridra backup was found.' }
        $latest.FullName
    }

    $testRoot = Join-Path $StateRoot ("recovery-test-" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    $identityDb = Join-Path $testRoot 'identity\veridra.sqlite3'
    $tenantRoot = Join-Path $testRoot 'tenants'
    New-Item -ItemType Directory -Force -Path $testRoot | Out-Null

    $wasRunning = [bool]((Get-VeridraProcess) -or (Get-MonitoringProcess))
    if ($wasRunning) {
        Write-Step 'Pausing Veridra while verifying isolated recovery...'
        Invoke-Stop
        Start-Sleep -Milliseconds 500
    }
    try {
        Write-Step "Restoring isolated test copy from: $archive"
        & $PythonExe -m veridra.backup_restore_cli restore `
            --archive $archive `
            --identity-db $identityDb `
            --tenant-data-root $tenantRoot `
            --confirm-quiesced
        if ($LASTEXITCODE -ne 0) { throw 'Isolated recovery test failed.' }
        & $PythonExe -c "import sqlite3,sys; db=sys.argv[1]; c=sqlite3.connect(db); r=c.execute('PRAGMA quick_check').fetchone()[0]; c.close(); print('sqlite_quick_check=' + str(r)); raise SystemExit(0 if r == 'ok' else 1)" $identityDb
        if ($LASTEXITCODE -ne 0) { throw 'Restored identity database integrity check failed.' }
        $restoredFiles = (Get-ChildItem $testRoot -Recurse -File).Count
        Write-Step "Isolated recovery PASS. Restored files: $restoredFiles"
        Write-Step "Recovery test root: $testRoot"
    } finally {
        if ($wasRunning) {
            Write-Step 'Restarting Veridra after recovery test...'
            Invoke-Start
        }
    }
}
function Invoke-Restore {
    if (-not $BackupPath) { throw 'Provide -BackupPath with a Veridra backup ZIP.' }
    if (-not (Test-Path $PythonExe)) { Invoke-Setup }
    $resolved = (Resolve-Path $BackupPath).Path
    $identityDb = Join-Path $DataRoot 'identity\veridra.sqlite3'
    $tenantRoot = Join-Path $DataRoot 'tenants'
    Write-Step "Restore source: $resolved"
    Write-Step "Restore identity target: $identityDb"
    Write-Step "Restore tenant target: $tenantRoot"
    if (-not $Apply) { Write-Step 'Preview only. Re-run with -Apply to restore.'; return }

    Invoke-Stop
    Ensure-Directories
    $safety = Join-Path $BackupRoot ("PRE_RESTORE_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.zip')
    if ((Test-Path $identityDb) -and (Test-Path $tenantRoot)) {
        Write-Step 'Creating verified pre-restore safety backup...'
        & $PythonExe -m veridra.backup_restore_cli backup `
            --output $safety `
            --identity-db $identityDb `
            --tenant-data-root $tenantRoot `
            --confirm-quiesced
        if ($LASTEXITCODE -ne 0) { throw 'Pre-restore safety backup failed; restore aborted.' }
    }

    Write-Step 'Applying verified restore...'
    & $PythonExe -m veridra.backup_restore_cli restore `
        --archive $resolved `
        --identity-db $identityDb `
        --tenant-data-root $tenantRoot `
        --confirm-quiesced `
        --replace-existing
    if ($LASTEXITCODE -ne 0) { throw 'Verified restore failed.' }
    Write-Step "Restore applied and verified. Safety backup: $safety"
}
function Invoke-Diagnostics {
    Ensure-Directories
    $output = Join-Path $RuntimeRoot ("VERIDRA_DIAGNOSTICS_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt')
    $web = Get-VeridraProcess
    $monitoring = Get-MonitoringProcess
    $lines = @(
        "Generated: $(Get-Date -Format o)",
        "Repository: $RepoRoot",
        "State root: $StateRoot",
        "Data root: $DataRoot",
        "Python executable: $PythonExe",
        "Python exists: $(Test-Path $PythonExe)",
        "Port: $Port",
        "URL: $Url",
        "Web process: $($web.Id)",
        "Monitoring process: $($monitoring.Id)",
        "SMTP configured: $(Test-Path $SmtpConfigFile)",
        "Stdout log: $StdoutLogFile",
        "Stderr log: $StderrLogFile",
        "Monitoring stdout: $MonitoringStdoutLogFile",
        "Monitoring stderr: $MonitoringStderrLogFile"
    )
    $lines | Set-Content -Path $output -Encoding utf8
    Write-Step "Diagnostics written: $output"
}
function Invoke-CreateShortcut {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'Veridra.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $RepoRoot 'VERIDRA_OPEN.bat'
    $shortcut.WorkingDirectory = $RepoRoot
    $shortcut.Description = 'Launch Veridra locally'
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
    $shortcut.Save()
    Write-Step "Desktop shortcut created: $shortcutPath"
}
function Invoke-RemoveShortcut {
    $path = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Veridra.lnk'
    Remove-Item $path -Force -ErrorAction SilentlyContinue
    Write-Step 'Desktop shortcut removed.'
}

switch ($Command) {
    'setup' { Invoke-Setup }
    'start' { Invoke-Start }
    'operator-start' { Invoke-OperatorStart }
    'stop' { Invoke-Stop }
    'restart' { Invoke-Stop; Invoke-Start }
    'operator-restart' { Invoke-OperatorRestart }
    'status' { Invoke-Status }
    'open' { Invoke-Open }
    'operator-open' { Invoke-OperatorOpen }
    'operator-preflight' { Invoke-OperatorPreflight }
    'test' { Invoke-Test }
    'backup' { Invoke-Backup }
    'restore' { Invoke-Restore }
    'recovery-test' { Invoke-RecoveryTest }
    'diagnostics' { Invoke-Diagnostics }
    'smtp-config' { Invoke-SmtpConfig }
    'smtp-test' { Invoke-SmtpTest }
    'create-shortcut' { Invoke-CreateShortcut }
    'remove-shortcut' { Invoke-RemoveShortcut }
}