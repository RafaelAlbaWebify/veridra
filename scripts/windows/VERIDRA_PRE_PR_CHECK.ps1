# VERIDRA pre-PR quality gate (Windows PowerShell)
# Run from repository root after activating the project Python environment.
# Exit immediately on the first failing check; never report readiness before all pass.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$checks = @(
    @('Ruff', @('-m', 'ruff', 'check', '.')),
    @('Strict mypy', @('-m', 'mypy', 'src', 'tests')),
    @('Pytest', @('-m', 'pytest'))
)
foreach ($check in $checks) {
    $name = $check[0]
    $arguments = $check[1]
    Write-Host "=== $name ==="
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$name failed (exit code $LASTEXITCODE). Do not open or merge the PR."
        exit $LASTEXITCODE
    }
}
Write-Host 'Local quality gate passed. CI and Windows acceptance are still required before merge.'
