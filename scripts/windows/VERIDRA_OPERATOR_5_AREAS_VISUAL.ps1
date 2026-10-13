# Read-only captures of five operator areas; output ZIP goes to Downloads.
param([ValidateRange(1,65535)][int]$Port = 8010)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Missing Python venv: $python" }
Push-Location $root
try {
    & $python tools/operator_five_area_visual.py --base-url "http://127.0.0.1:$Port" --output-dir (Join-Path $HOME 'Downloads')
    if ($LASTEXITCODE -ne 0) { throw "Operator visual acceptance failed ($LASTEXITCODE)" }
} finally {
    Pop-Location
}
