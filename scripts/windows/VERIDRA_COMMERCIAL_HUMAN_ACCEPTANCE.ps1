# Isolated human acceptance: never launch against the active commercial data root.
param(
    [ValidateSet('prepare','start','stop','status')]
    [string]$Command = 'prepare',
    [string]$SessionDirectory = '',
    [int]$Port = 18011
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Commercial = Join-Path $PSScriptRoot 'veridra-commercial-local.ps1'
$Legacy = Join-Path $PSScriptRoot 'veridra-human-acceptance.ps1'
$Downloads = Join-Path $env:USERPROFILE 'Downloads'

if ($Command -eq 'prepare') {
    $SessionDirectory = Join-Path $Downloads ('VERIDRA_COMMERCIAL_HUMAN_ACCEPTANCE_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    if (Test-Path -LiteralPath $SessionDirectory) { throw 'Session already exists; refusing to reuse.' }
    New-Item -ItemType Directory -Path $SessionDirectory | Out-Null
    foreach ($name in @('screenshots','diagnostics','localappdata')) {
        New-Item -ItemType Directory -Path (Join-Path $SessionDirectory $name) | Out-Null
    }
    $legacyContent = Get-Content -LiteralPath $Legacy -Raw
    $pattern = '(?s)\$checklistText = @' + [char]39 + '\r?\n(.*?)\r?\n' + [char]39 + '@'
    $match = [regex]::Match($legacyContent, $pattern)
    if (-not $match.Success) { throw 'Cannot extract existing human acceptance checklist safely.' }
    $checklist = $match.Groups[1].Value
    $checklist = $checklist.Replace('## 16 — Backup / restore', '## 16 — Backup / restore (only within this isolated session)')
    Set-Content -LiteralPath (Join-Path $SessionDirectory 'CHECKLIST.md') -Value $checklist -Encoding utf8
    Set-Content -LiteralPath (Join-Path $SessionDirectory 'DEFECTS.md') -Value '# VERIDRA commercial operator defects (synthetic only)' -Encoding utf8
    $head = & git -C $RepoRoot rev-parse HEAD
    @(
        'VERIDRA isolated commercial human acceptance'
        "Repo: $RepoRoot"
        "Commit: $head"
        "Port: $Port"
        'Production %LOCALAPPDATA%\VeridraCommercial is NOT used.'
        'Data is kept inside this session folder under localappdata\VeridraCommercial.'
        'Synthetic data only; no outreach, real billing or external customer delivery.'
        'Run start/status/stop with -SessionDirectory pointing to this exact folder.'
        'Human PASS must be recorded manually; automated checks are not enough.'
    ) | Set-Content -LiteralPath (Join-Path $SessionDirectory 'SESSION.txt') -Encoding utf8
    Write-Host "[HUMAN ACCEPTANCE] Prepared: $SessionDirectory"
    Write-Host "Run: & '.\scripts\windows\VERIDRA_COMMERCIAL_HUMAN_ACCEPTANCE.ps1' -Command start -SessionDirectory '$SessionDirectory'"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($SessionDirectory)) {
    throw 'For start/stop/status, supply -SessionDirectory from prepare output.'
}
$resolved = [System.IO.Path]::GetFullPath($SessionDirectory)
$sessionLeaf = Split-Path $resolved -Leaf
if (-not $sessionLeaf.StartsWith('VERIDRA_COMMERCIAL_HUMAN_ACCEPTANCE_')) {
    throw 'Refusing a non-acceptance session path.'
}
if (-not (Test-Path -LiteralPath (Join-Path $resolved 'SESSION.txt') -PathType Leaf)) {
    throw 'Missing session marker. Refusing to use supplied path.'
}
$isolatedLocalAppData = Join-Path $resolved 'localappdata'
if (-not (Test-Path -LiteralPath $isolatedLocalAppData -PathType Container)) {
    throw 'Missing isolated state root.'
}
$expectedProduction = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'VeridraCommercial'
$isolationTarget = Join-Path $isolatedLocalAppData 'VeridraCommercial'
if ([System.IO.Path]::GetFullPath($expectedProduction).TrimEnd('\') -ieq [System.IO.Path]::GetFullPath($isolationTarget).TrimEnd('\')) {
    throw 'Isolation failed: refusing production state.'
}
if ($Command -eq 'start') {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        $pidFile = Join-Path $isolationTarget 'runtime\veridra-commercial.pid'
        if (-not (Test-Path -LiteralPath $pidFile)) {
            throw "Port $Port is occupied without a PID recorded in this isolated session."
        }
        $recordedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        if ($recordedPid -notmatch '^\d+$') {
            throw 'Isolated PID file contains an invalid process ID.'
        }
        $foreignListeners = @($listeners | Where-Object {
            $_.OwningProcess -ne [int]$recordedPid
        })
        if ($foreignListeners.Count -gt 0) {
            throw "Port $Port is not owned by this session's recorded web process."
        }
    }
}
# Only this session's child process receives the isolated local-appdata root.
$previousLocalAppData = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $isolatedLocalAppData
    if ($Command -eq 'start') {
        $python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $python)) { throw 'Missing project Python venv.' }
        $syntheticDataRoot = Join-Path $isolationTarget 'data'
        $identityDb = Join-Path $syntheticDataRoot 'identity\veridra.sqlite3'
        $tenantRoot = Join-Path $syntheticDataRoot 'tenants'
        & $python -m veridra.local_operator_bootstrap --database $identityDb --tenant-data-root $tenantRoot
        if ($LASTEXITCODE -ne 0) { throw 'Isolated owner initialization failed.' }
        & $Commercial open -Port $Port
    } elseif ($Command -eq 'stop') {
        & $Commercial stop -Port $Port
    } else {
        & $Commercial status -Port $Port
    }
    if ($LASTEXITCODE -ne 0) { throw "Isolated commercial $Command failed." }
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
}
