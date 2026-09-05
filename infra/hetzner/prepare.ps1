param(
    [Parameter(Mandatory = $true)]
    [string]$SshCidr,

    [string]$SshPublicKeyPath = "$HOME\.ssh\id_ed25519.pub",

    [string]$ServerName = "veridra-prod-1",

    [string]$Location = "nbg1",

    [string]$ServerType = "cx33"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

if ($SshCidr -in @('0.0.0.0/0', '::/0')) {
    throw 'Refusing an open-to-world SSH CIDR. Supply only the operator public IP/network.'
}

if ($SshCidr -notmatch '^[0-9A-Fa-f:.]+/[0-9]{1,3}$') {
    throw 'SshCidr must be CIDR notation, for example 203.0.113.42/32.'
}

if (-not (Test-Path -LiteralPath $SshPublicKeyPath)) {
    throw "SSH public key not found at '$SshPublicKeyPath'. Create one with ssh-keygen -t ed25519 or pass -SshPublicKeyPath."
}

$PublicKey = (Get-Content -LiteralPath $SshPublicKeyPath -Raw).Trim()
if ($PublicKey -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)\s+') {
    throw 'The selected file does not look like a supported OpenSSH public key.'
}

function Escape-HclString([string]$Value) {
    return $Value.Replace('\\', '\\\\').Replace('"', '\"')
}

$Tfvars = @"
server_name = "$(Escape-HclString $ServerName)"
location    = "$(Escape-HclString $Location)"
server_type = "$(Escape-HclString $ServerType)"
ssh_public_key = "$(Escape-HclString $PublicKey)"
ssh_source_cidrs = ["$(Escape-HclString $SshCidr)"]
"@

$Target = Join-Path $Here 'terraform.tfvars'
Set-Content -LiteralPath $Target -Value $Tfvars -Encoding utf8NoBOM

Write-Host "Created $Target"
Write-Host 'Contains only the SSH public key and infrastructure settings; no HCLOUD_TOKEN is written.'
Write-Host 'Review it, then run .\provision.ps1 for a plan-only validation.'
