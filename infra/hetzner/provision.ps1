param(
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
    throw 'Terraform is not installed or not available in PATH.'
}

if ([string]::IsNullOrWhiteSpace($env:HCLOUD_TOKEN)) {
    throw 'HCLOUD_TOKEN is not set in this PowerShell session. Set it securely; do not put it in terraform.tfvars or Git.'
}

if (-not (Test-Path '.\terraform.tfvars')) {
    throw 'terraform.tfvars is missing. Copy terraform.tfvars.example, replace the public SSH key and trusted SSH CIDR, then rerun.'
}

Write-Host 'VERIDRA Hetzner provisioning validation'
Write-Host 'Token detected in process environment (value will not be printed).'

terraform init
if ($LASTEXITCODE -ne 0) { throw 'terraform init failed.' }

terraform fmt -check
if ($LASTEXITCODE -ne 0) { throw 'terraform fmt -check failed.' }

terraform validate
if ($LASTEXITCODE -ne 0) { throw 'terraform validate failed.' }

$PlanFile = Join-Path $Here 'veridra.tfplan'
terraform plan -out=$PlanFile
if ($LASTEXITCODE -ne 0) { throw 'terraform plan failed.' }

if (-not $Apply) {
    Write-Host ''
    Write-Host 'Plan created successfully. No infrastructure was changed.'
    Write-Host 'Review the plan, then rerun with -Apply to provision the server.'
    exit 0
}

Write-Host ''
Write-Host 'Applying the reviewed Terraform plan...'
terraform apply $PlanFile
if ($LASTEXITCODE -ne 0) { throw 'terraform apply failed.' }

Write-Host ''
Write-Host 'Provisioning completed. Public outputs:'
terraform output
Write-Host ''
Write-Host 'Next: create DNS A/AAAA records and follow docs/operations/first-host-acceptance.md.'
