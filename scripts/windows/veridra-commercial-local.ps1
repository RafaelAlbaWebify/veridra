param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('start','open','stop','restart','status','preflight','backup','recovery-test','tenants','stripe-config','stripe-clear','provider-preflight','provider-snapshot','provider-reconcile','stripe-listen','h6-phase3','h6-phase4','h6-phase5','h6-phase6')]
    [string]$Command,
    [ValidateRange(1,65535)]
    [int]$Port = 8011,
    [string]$BackupPath,
    [string]$TenantId,
    [string]$TenantDataRoot,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateRoot = Join-Path $env:LOCALAPPDATA 'VeridraCommercial'
$DataRoot = Join-Path $StateRoot 'data'
$RuntimeRoot = Join-Path $StateRoot 'runtime'
$BackupRoot = Join-Path $StateRoot 'backups'
$ConfigRoot = Join-Path $StateRoot 'config'
$StripeConfigFile = Join-Path $ConfigRoot 'stripe.json'
$StripeSecretKeyFile = Join-Path $ConfigRoot 'stripe-secret-key.txt'
$StripeWebhookSecretFile = Join-Path $ConfigRoot 'stripe-webhook-secret.txt'
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

function Clear-StripeEnvironment {
    foreach ($name in @(
        'VERIDRA_STRIPE_SECRET_KEY',
        'VERIDRA_STRIPE_WEBHOOK_SECRET',
        'VERIDRA_STRIPE_PRICE_SOLO',
        'VERIDRA_STRIPE_PRICE_PROFESSIONAL',
        'VERIDRA_STRIPE_PRICE_AGENCY'
    )) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
}

function Ensure-NativeDpapi {
    if ('VeridraNativeDpapi' -as [type]) { return }
    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class VeridraNativeDpapi
{
    [StructLayout(LayoutKind.Sequential)]
    private struct DATA_BLOB
    {
        public int cbData;
        public IntPtr pbData;
    }

    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CryptProtectData(
        ref DATA_BLOB pDataIn,
        string szDataDescr,
        IntPtr pOptionalEntropy,
        IntPtr pvReserved,
        IntPtr pPromptStruct,
        int dwFlags,
        out DATA_BLOB pDataOut);

    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CryptUnprotectData(
        ref DATA_BLOB pDataIn,
        IntPtr ppszDataDescr,
        IntPtr pOptionalEntropy,
        IntPtr pvReserved,
        IntPtr pPromptStruct,
        int dwFlags,
        out DATA_BLOB pDataOut);

    [DllImport("kernel32.dll", SetLastError = false)]
    private static extern IntPtr LocalFree(IntPtr hMem);

    private static DATA_BLOB BlobFromBytes(byte[] bytes)
    {
        var blob = new DATA_BLOB();
        blob.cbData = bytes.Length;
        blob.pbData = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, blob.pbData, bytes.Length);
        return blob;
    }

    private static byte[] BytesFromBlob(DATA_BLOB blob)
    {
        var bytes = new byte[blob.cbData];
        Marshal.Copy(blob.pbData, bytes, 0, blob.cbData);
        return bytes;
    }

    public static string Protect(string plaintext)
    {
        var inputBytes = Encoding.UTF8.GetBytes(plaintext);
        var input = BlobFromBytes(inputBytes);
        DATA_BLOB output;
        try
        {
            if (!CryptProtectData(ref input, "VERIDRA local Stripe secret", IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0, out output))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            try
            {
                return Convert.ToBase64String(BytesFromBlob(output));
            }
            finally
            {
                if (output.pbData != IntPtr.Zero) LocalFree(output.pbData);
            }
        }
        finally
        {
            Array.Clear(inputBytes, 0, inputBytes.Length);
            if (input.pbData != IntPtr.Zero) Marshal.FreeHGlobal(input.pbData);
        }
    }

    public static string Unprotect(string encoded)
    {
        var protectedBytes = Convert.FromBase64String(encoded);
        var input = BlobFromBytes(protectedBytes);
        DATA_BLOB output;
        try
        {
            if (!CryptUnprotectData(ref input, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0, out output))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            try
            {
                var bytes = BytesFromBlob(output);
                try
                {
                    return Encoding.UTF8.GetString(bytes);
                }
                finally
                {
                    Array.Clear(bytes, 0, bytes.Length);
                }
            }
            finally
            {
                if (output.pbData != IntPtr.Zero) LocalFree(output.pbData);
            }
        }
        finally
        {
            Array.Clear(protectedBytes, 0, protectedBytes.Length);
            if (input.pbData != IntPtr.Zero) Marshal.FreeHGlobal(input.pbData);
        }
    }
}
"@
}

function Protect-LocalSecret([string]$PlainText) {
    Ensure-NativeDpapi
    return [VeridraNativeDpapi]::Protect($PlainText)
}

function Read-ProtectedSecret([string]$Path,[string]$Label) {
    if (-not (Test-Path $Path)) { throw "$Label secret file is missing." }
    $encoded = (Get-Content $Path -Raw).Trim()
    try {
        Ensure-NativeDpapi
        return [VeridraNativeDpapi]::Unprotect($encoded)
    } catch {
        throw "$Label secret file could not be decrypted for the current Windows user."
    }
}

function Import-StripeEnvironment {
    Clear-StripeEnvironment
    if (-not (Test-Path $StripeConfigFile)) { return }
    if (-not (Test-Path $StripeSecretKeyFile) -or -not (Test-Path $StripeWebhookSecretFile)) {
        throw 'Stripe configuration exists but encrypted secret files are missing.'
    }
    $config = Get-Content $StripeConfigFile -Raw | ConvertFrom-Json
    foreach ($property in @('price_solo','price_professional','price_agency')) {
        $value = [string]$config.$property
        if (-not $value -or -not $value.StartsWith('price_')) {
            throw "Stripe configuration property $property is invalid."
        }
    }
    $env:VERIDRA_STRIPE_SECRET_KEY = Read-ProtectedSecret $StripeSecretKeyFile 'stripe-api'
    $env:VERIDRA_STRIPE_WEBHOOK_SECRET = Read-ProtectedSecret $StripeWebhookSecretFile 'stripe-webhook'
    $env:VERIDRA_STRIPE_PRICE_SOLO = [string]$config.price_solo
    $env:VERIDRA_STRIPE_PRICE_PROFESSIONAL = [string]$config.price_professional
    $env:VERIDRA_STRIPE_PRICE_AGENCY = [string]$config.price_agency
}

function Set-CommercialEnvironment {
    $env:VERIDRA_ENV = 'production'
    $env:VERIDRA_BIND_HOST = '127.0.0.1'
    $env:VERIDRA_BIND_PORT = "$Port"
    $env:VERIDRA_ALLOWED_HOSTS = '127.0.0.1,localhost'
    $env:VERIDRA_TRUSTED_ORIGIN = $Url.TrimEnd('/')
    $env:VERIDRA_LOCAL_AUTOLOGIN = '1'
    $env:VERIDRA_IDENTITY_DB = Join-Path $DataRoot 'identity\veridra.sqlite3'
    $env:VERIDRA_TENANT_DATA_ROOT = Join-Path $DataRoot 'tenants'
    Import-StripeEnvironment
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
    Write-Step ("Stripe test config: " + $(if (Test-Path $StripeConfigFile) { 'configured' } else { 'not configured' }))
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

function Get-StripeCommand {
    $command = Get-Command stripe -ErrorAction SilentlyContinue
    if (-not $command) {
        throw 'Stripe CLI was not found in PATH. Install the official Stripe CLI and run stripe login before H6 provider acceptance.'
    }
    return $command.Source
}

function Invoke-StripeConfig {
    Ensure-Directories
    $stripe = Get-StripeCommand
    Write-Step 'Stripe CLI detected. The CLI must be authenticated in test mode (stripe login).'

    $priceSolo = (Read-Host 'Stripe Price ID for Solo').Trim()
    $priceProfessional = (Read-Host 'Stripe Price ID for Professional').Trim()
    $priceAgency = (Read-Host 'Stripe Price ID for Agency').Trim()
    $prices = @($priceSolo,$priceProfessional,$priceAgency)
    if ($prices | Where-Object { -not $_.StartsWith('price_') }) {
        throw 'All Stripe plan mappings must be Price IDs beginning with price_.'
    }
    if (($prices | Select-Object -Unique).Count -ne 3) {
        throw 'Solo, Professional and Agency must use distinct Stripe Price IDs.'
    }

    $apiSecret = Read-Host 'Stripe TEST secret key (sk_test_...)' -AsSecureString
    $apiCredential = New-Object System.Management.Automation.PSCredential('stripe-api', $apiSecret)
    $apiPlain = $apiCredential.GetNetworkCredential().Password
    if (-not $apiPlain.StartsWith('sk_test_')) {
        throw 'Only a Stripe test-mode secret key (sk_test_...) is accepted for H6.'
    }

    Write-Step 'Reading the local Stripe CLI webhook signing secret without printing it...'
    $webhookPlain = (& $stripe listen --print-secret 2>$null | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $webhookPlain.StartsWith('whsec_')) {
        throw 'Stripe CLI could not provide a webhook secret. Run stripe login and retry.'
    }
    [ordered]@{
        price_solo = $priceSolo
        price_professional = $priceProfessional
        price_agency = $priceAgency
        mode = 'test'
    } | ConvertTo-Json | Set-Content -Path $StripeConfigFile -Encoding utf8
    Protect-LocalSecret $apiPlain | Set-Content -Path $StripeSecretKeyFile -Encoding ascii
    Protect-LocalSecret $webhookPlain | Set-Content -Path $StripeWebhookSecretFile -Encoding ascii

    $apiPlain = $null
    $webhookPlain = $null
    Write-Step "Stripe test configuration saved outside the repository: $StripeConfigFile"
    Write-Step 'Restart the commercial runtime before using paid-plan flows.'
}

function Invoke-StripeClear {
    Clear-StripeEnvironment
    Remove-Item $StripeConfigFile,$StripeSecretKeyFile,$StripeWebhookSecretFile -Force -ErrorAction SilentlyContinue
    Write-Step 'Local commercial Stripe configuration removed.'
}

function Invoke-Tenants {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    & $PythonExe -m veridra.local_commercial_tenants
    if ($LASTEXITCODE -ne 0) {
        throw 'Commercial tenant listing failed.'
    }
}

function Invoke-ProviderPreflight {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    if (-not (Test-Path $StripeConfigFile)) {
        throw 'Stripe is not configured. Run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat first.'
    }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $output = Join-Path $HOME "Downloads\VERIDRA_COMMERCIAL_PROVIDER_PREFLIGHT_$stamp.json"
    Write-Step 'Running real Stripe test-mode provider preflight...'
    & $PythonExe -m veridra.hosted_provider_preflight --output $output
    if ($LASTEXITCODE -ne 0) { throw 'Commercial provider preflight failed.' }
    Write-Step "Provider preflight PASS. Evidence: $output"
}

function Invoke-ProviderSnapshot {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    $checkedTenant = if ($TenantId) {
        $TenantId.Trim().ToLowerInvariant()
    } else {
        (Read-Host 'Tenant ID').Trim().ToLowerInvariant()
    }
    if ($checkedTenant -notmatch '^[0-9a-f]{24}$') {
        throw 'Tenant ID must be 24 lowercase hexadecimal characters.'
    }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $filename = 'VERIDRA_COMMERCIAL_PROVIDER_STATE_' + $checkedTenant + '_' + $stamp + '.json'
    $output = Join-Path $HOME ('Downloads\' + $filename)
    $snapshotArgs = @(
        '-m','veridra.local_provider_snapshot',
        '--tenant-id',$checkedTenant,
        '--output',$output
    )
    if ($TenantDataRoot) {
        $resolvedTenantRoot = (Resolve-Path $TenantDataRoot).Path
        $snapshotArgs += @('--tenant-data-root',$resolvedTenantRoot)
        Write-Step "Capturing provider state from explicit tenant root: $resolvedTenantRoot"
    }
    & $PythonExe @snapshotArgs
    if ($LASTEXITCODE -ne 0) { throw 'Commercial provider state snapshot failed.' }
    Write-Step "Provider state snapshot: $output"
}

function Invoke-ProviderReconcile {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    if (-not (Test-Path $StripeConfigFile)) {
        throw 'Stripe is not configured. Run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat first.'
    }
    $checkedTenant = if ($TenantId) {
        $TenantId.Trim().ToLowerInvariant()
    } else {
        (Read-Host 'Tenant ID').Trim().ToLowerInvariant()
    }
    if ($checkedTenant -notmatch '^[0-9a-f]{24}$') {
        throw 'Tenant ID must be 24 lowercase hexadecimal characters.'
    }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $mode = if ($Apply.IsPresent) { 'APPLY' } else { 'CHECK' }
    $filename = 'VERIDRA_COMMERCIAL_PROVIDER_RECONCILIATION_' + $mode + '_' + $checkedTenant + '_' + $stamp + '.json'
    $output = Join-Path $HOME ('Downloads\' + $filename)
    $reconcileArgs = @(
        '-m','veridra.local_provider_reconcile',
        '--tenant-id',$checkedTenant,
        '--output',$output
    )
    if ($TenantDataRoot) {
        $resolvedTenantRoot = (Resolve-Path $TenantDataRoot).Path
        $reconcileArgs += @('--tenant-data-root',$resolvedTenantRoot)
        Write-Step "Reconciling explicit tenant root: $resolvedTenantRoot"
    }
    if ($Apply.IsPresent) {
        $reconcileArgs += '--apply'
        Write-Step 'Applying authoritative Stripe state only if drift is detected.'
    } else {
        Write-Step 'Checking Stripe vs VERIDRA state read-only. Use -Apply only after reviewing drift.'
    }
    & $PythonExe @reconcileArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'Commercial provider reconciliation failed.'
    }
    Write-Step "Provider reconciliation evidence: $output"
}

function Invoke-StripeListen {
    Ensure-Directories
    $stripe = Get-StripeCommand
    Set-CommercialEnvironment
    if (-not $env:VERIDRA_STRIPE_WEBHOOK_SECRET) {
        throw 'Stripe is not configured. Run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat first.'
    }

    $currentSecret = (& $stripe listen --print-secret 2>$null | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $currentSecret.StartsWith('whsec_')) {
        throw 'Stripe CLI could not provide its current webhook signing secret.'
    }
    if ($currentSecret -ne $env:VERIDRA_STRIPE_WEBHOOK_SECRET) {
        throw 'Stripe CLI webhook secret changed. Re-run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat, then restart VERIDRA.'
    }
    $currentSecret = $null

    $endpoint = "http://127.0.0.1:$Port/api/billing/stripe/webhook"
    $events = 'customer.subscription.created,customer.subscription.updated,customer.subscription.deleted'
    Write-Step "Forwarding Stripe TEST events to $endpoint"
    Write-Step 'Keep this window open during H6 billing acceptance. No public endpoint is required.'
    & $stripe listen --events $events --forward-to $endpoint
    if ($LASTEXITCODE -ne 0) { throw 'Stripe CLI listener exited with an error.' }
}

function Invoke-H6Phase3 {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    if (-not (Test-Path $StripeConfigFile)) {
        throw 'Stripe is not configured. Run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat first.'
    }
    $checkedTenant = if ($TenantId) {
        $TenantId.Trim().ToLowerInvariant()
    } else {
        (Read-Host 'Tenant ID').Trim().ToLowerInvariant()
    }
    if ($checkedTenant -notmatch '^[0-9a-f]{24}$') {
        throw 'Tenant ID must be 24 lowercase hexadecimal characters.'
    }

    $stripe = Get-StripeCommand
    $currentSecret = (& $stripe listen --print-secret 2>$null | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $currentSecret.StartsWith('whsec_')) {
        throw 'Stripe CLI could not provide its current webhook signing secret.'
    }
    if ($currentSecret -ne $env:VERIDRA_STRIPE_WEBHOOK_SECRET) {
        throw 'Stripe CLI webhook secret changed. Re-run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat, then restart VERIDRA.'
    }
    $currentSecret = $null

    $endpoint = "http://127.0.0.1:$Port/api/billing/stripe/webhook"
    $events = 'customer.subscription.created,customer.subscription.updated,customer.subscription.deleted'
    $listenerOut = Join-Path $RuntimeRoot 'h6-phase3-stripe-listener.stdout.log'
    $listenerErr = Join-Path $RuntimeRoot 'h6-phase3-stripe-listener.stderr.log'
    Remove-Item $listenerOut,$listenerErr -Force -ErrorAction SilentlyContinue

    Write-Step 'Starting temporary Stripe listener for automated H6 Phase 3...'
    $listener = Start-Process -FilePath $stripe -ArgumentList @('listen','--events',$events,'--forward-to',$endpoint) -RedirectStandardOutput $listenerOut -RedirectStandardError $listenerErr -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    if ($listener.HasExited) {
        throw "Stripe listener stopped unexpectedly. Review $listenerErr"
    }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $output = Join-Path $HOME "Downloads\VERIDRA_COMMERCIAL_H6_PHASE3_$stamp.json"
    try {
        Write-Step 'Running automated H6 Phase 3: portal check, Solo -> Professional -> Solo...'
        & $PythonExe -m veridra.local_h6_acceptance --tenant-id $checkedTenant --output $output
        if ($LASTEXITCODE -ne 0) {
            throw "Automated H6 Phase 3 failed. Review $listenerErr"
        }
    } finally {
        if ($listener -and -not $listener.HasExited) {
            Stop-Process -Id $listener.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Step "Automated H6 Phase 3 PASS. Evidence: $output"
}
function Invoke-H6Phase4 {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    if (-not (Test-Path $StripeConfigFile)) {
        throw 'Stripe is not configured. Run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat first.'
    }
    $checkedTenant = if ($TenantId) {
        $TenantId.Trim().ToLowerInvariant()
    } else {
        (Read-Host 'Tenant ID').Trim().ToLowerInvariant()
    }
    if ($checkedTenant -notmatch '^[0-9a-f]{24}$') {
        throw 'Tenant ID must be 24 lowercase hexadecimal characters.'
    }

    $stripe = Get-StripeCommand
    $currentSecret = (& $stripe listen --print-secret 2>$null | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $currentSecret.StartsWith('whsec_')) {
        throw 'Stripe CLI could not provide its current webhook signing secret.'
    }
    if ($currentSecret -ne $env:VERIDRA_STRIPE_WEBHOOK_SECRET) {
        throw 'Stripe CLI webhook secret changed. Re-run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat, then restart VERIDRA.'
    }
    $currentSecret = $null

    $endpoint = "http://127.0.0.1:$Port/api/billing/stripe/webhook"
    $events = 'customer.subscription.created,customer.subscription.updated,customer.subscription.deleted'
    $listenerOut = Join-Path $RuntimeRoot 'h6-phase4-stripe-listener.stdout.log'
    $listenerErr = Join-Path $RuntimeRoot 'h6-phase4-stripe-listener.stderr.log'
    Remove-Item $listenerOut,$listenerErr -Force -ErrorAction SilentlyContinue

    Write-Step 'Starting temporary Stripe listener for automated H6 Phase 4...'
    $listener = Start-Process -FilePath $stripe -ArgumentList @('listen','--events',$events,'--forward-to',$endpoint) -RedirectStandardOutput $listenerOut -RedirectStandardError $listenerErr -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    if ($listener.HasExited) {
        throw "Stripe listener stopped unexpectedly. Review $listenerErr"
    }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $output = Join-Path $HOME "Downloads\VERIDRA_COMMERCIAL_H6_PHASE4_$stamp.json"
    try {
        Write-Step 'Running automated H6 Phase 4: payment failure -> suspended -> recovery -> active...'
        & $PythonExe -m veridra.local_h6_phase4 --tenant-id $checkedTenant --output $output
        if ($LASTEXITCODE -ne 0) {
            throw "Automated H6 Phase 4 failed. Review $listenerErr"
        }
    } finally {
        if ($listener -and -not $listener.HasExited) {
            Stop-Process -Id $listener.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Step "Automated H6 Phase 4 PASS. Evidence: $output"
}
function Invoke-H6Phase5 {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    if (-not (Test-Path $StripeConfigFile)) {
        throw 'Stripe is not configured. Run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat first.'
    }
    $checkedTenant = if ($TenantId) {
        $TenantId.Trim().ToLowerInvariant()
    } else {
        (Read-Host 'Tenant ID').Trim().ToLowerInvariant()
    }
    if ($checkedTenant -notmatch '^[0-9a-f]{24}$') {
        throw 'Tenant ID must be 24 lowercase hexadecimal characters.'
    }

    $stripe = Get-StripeCommand
    $currentSecret = (& $stripe listen --print-secret 2>$null | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $currentSecret.StartsWith('whsec_')) {
        throw 'Stripe CLI could not provide its current webhook signing secret.'
    }
    if ($currentSecret -ne $env:VERIDRA_STRIPE_WEBHOOK_SECRET) {
        throw 'Stripe CLI webhook secret changed. Re-run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat, then restart VERIDRA.'
    }
    $currentSecret = $null

    $endpoint = "http://127.0.0.1:$Port/api/billing/stripe/webhook"
    $events = 'customer.subscription.created,customer.subscription.updated,customer.subscription.deleted'
    $listenerOut = Join-Path $RuntimeRoot 'h6-phase5-stripe-listener.stdout.log'
    $listenerErr = Join-Path $RuntimeRoot 'h6-phase5-stripe-listener.stderr.log'
    Remove-Item $listenerOut,$listenerErr -Force -ErrorAction SilentlyContinue

    Write-Step 'Starting temporary Stripe listener for automated H6 Phase 5...'
    $listener = Start-Process -FilePath $stripe -ArgumentList @('listen','--events',$events,'--forward-to',$endpoint) -RedirectStandardOutput $listenerOut -RedirectStandardError $listenerErr -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    if ($listener.HasExited) {
        throw "Stripe listener stopped unexpectedly. Review $listenerErr"
    }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $output = Join-Path $HOME "Downloads\VERIDRA_COMMERCIAL_H6_PHASE5_$stamp.json"
    try {
        Write-Step 'Running automated H6 Phase 5: cancel -> suspended -> replacement -> active -> obsolete deletion guard...'
        & $PythonExe -m veridra.local_h6_phase5 --tenant-id $checkedTenant --output $output
        if ($LASTEXITCODE -ne 0) {
            throw "Automated H6 Phase 5 failed. Review $listenerErr"
        }
    } finally {
        if ($listener -and -not $listener.HasExited) {
            Stop-Process -Id $listener.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Step "Automated H6 Phase 5 PASS. Evidence: $output"
}
function Invoke-H6Phase6 {
    Ensure-Directories
    Ensure-Python
    Set-CommercialEnvironment
    if (-not (Test-Path $StripeConfigFile)) {
        throw 'Stripe is not configured. Run VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat first.'
    }
    $checkedTenant = if ($TenantId) { $TenantId.Trim().ToLowerInvariant() } else { (Read-Host 'Tenant ID').Trim().ToLowerInvariant() }
    if ($checkedTenant -notmatch '^[0-9a-f]{24}$') { throw 'Tenant ID must be 24 lowercase hexadecimal characters.' }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backup = Join-Path $BackupRoot "VERIDRA_COMMERCIAL_H6_PHASE6_BACKUP_$stamp.zip"
    $recoveryRoot = Join-Path $StateRoot "h6-phase6-recovery-$stamp"
    $output = Join-Path $HOME "Downloads\VERIDRA_COMMERCIAL_H6_PHASE6_$stamp.json"
    $wasRunning = [bool](
        (Get-ManagedProcess $PidFile '-m veridra.runtime') -or
        (Get-ManagedProcess $MonitoringPidFile '-m veridra.monitoring_service') -or
        (Get-ManagedProcess $CrawlPidFile '-m veridra.crawl_worker_service')
    )
    if ($wasRunning) { Invoke-Stop }
    try {
        Write-Step 'Running automated H6 Phase 6: backup -> isolated restore -> reconcile -> stale/replay proof...'
        & $PythonExe -m veridra.local_h6_phase6 --tenant-id $checkedTenant --identity-db $env:VERIDRA_IDENTITY_DB --tenant-data-root $env:VERIDRA_TENANT_DATA_ROOT --backup-path $backup --recovery-root $recoveryRoot --output $output
        if ($LASTEXITCODE -ne 0) { throw 'Automated H6 Phase 6 failed.' }
    } finally {
        if ($wasRunning) { Invoke-Start }
    }
    Write-Step "Automated H6 Phase 6 PASS. Evidence: $output"
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

switch ($Command) {
    'start' { Invoke-Start }
    'open' { Invoke-Start; Start-Process ($Url.TrimEnd('/') + '/signup') }
    'stop' { Invoke-Stop }
    'restart' { Invoke-Stop; Invoke-Start }
    'status' { Invoke-Status }
    'preflight' { Invoke-Preflight }
    'backup' { Invoke-Backup }
    'recovery-test' { Invoke-RecoveryTest }
    'tenants' { Invoke-Tenants }
    'stripe-config' { Invoke-StripeConfig }
    'stripe-clear' { Invoke-StripeClear }
    'provider-preflight' { Invoke-ProviderPreflight }
    'provider-snapshot' { Invoke-ProviderSnapshot }
    'provider-reconcile' { Invoke-ProviderReconcile }
    'stripe-listen' { Invoke-StripeListen }
    'h6-phase3' { Invoke-H6Phase3 }
    'h6-phase4' { Invoke-H6Phase4 }
    'h6-phase5' { Invoke-H6Phase5 }
    'h6-phase6' { Invoke-H6Phase6 }
}
