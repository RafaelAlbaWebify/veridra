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

terraform init -input=false
if ($LASTEXITCODE -ne 0) { throw 'terraform init failed.' }

terraform fmt -check -recursive
if ($LASTEXITCODE -ne 0) { throw 'terraform fmt -check failed.' }

terraform validate -no-color
if ($LASTEXITCODE -ne 0) { throw 'terraform validate failed.' }

$PlanFile = Join-Path $Here 'veridra.tfplan'
if (Test-Path $PlanFile) {
    Remove-Item -LiteralPath $PlanFile -Force
}

terraform plan -input=false -out=$PlanFile
if ($LASTEXITCODE -ne 0) { throw 'terraform plan failed.' }

if (-not $Apply) {
    Write-Host ''
    Write-Host 'Plan created successfully. No infrastructure was changed.'
    Write-Host 'Review the plan with: terraform show veridra.tfplan'
    Write-Host 'Then rerun with -Apply to provision exactly that planned configuration.'
    exit 0
}

Write-Host ''
Write-Host 'Applying the reviewed Terraform plan...'
terraform apply -input=false $PlanFile
if ($LASTEXITCODE -ne 0) { throw 'terraform apply failed.' }

Remove-Item -LiteralPath $PlanFile -Force -ErrorAction SilentlyContinue

Write-Host ''
Write-Host 'Provisioning completed. Public outputs:'
terraform output
Write-Host ''
Write-Host 'Next: create DNS A/AAAA records and follow docs/operations/first-host-acceptance.md.'
