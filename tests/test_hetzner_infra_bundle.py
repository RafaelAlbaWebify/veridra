from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra" / "hetzner"


def test_terraform_pins_current_provider_family_and_uses_location() -> None:
    versions = (INFRA / "versions.tf").read_text(encoding="utf-8")
    main = (INFRA / "main.tf").read_text(encoding="utf-8")

    assert 'source  = "hetznercloud/hcloud"' in versions
    assert 'version = "~> 1.68"' in versions
    assert "location    = var.location" in main
    assert "datacenter" not in main


def test_firewall_never_exposes_application_port_and_restricts_ssh() -> None:
    main = (INFRA / "main.tf").read_text(encoding="utf-8")
    variables = (INFRA / "variables.tf").read_text(encoding="utf-8")
    example = (INFRA / "terraform.tfvars.example").read_text(encoding="utf-8")

    assert 'port        = "22"' in main
    assert "source_ips  = var.ssh_source_cidrs" in main
    assert 'port        = "80"' in main
    assert 'port        = "443"' in main
    assert 'port        = "8000"' not in main
    assert "length(var.ssh_source_cidrs) > 0" in variables
    assert "Do not use 0.0.0.0/0 or ::/0 for SSH" in example


def test_server_starts_with_firewall_backup_and_protection() -> None:
    main = (INFRA / "main.tf").read_text(encoding="utf-8")

    assert "firewall_ids = [hcloud_firewall.veridra.id]" in main
    assert "backups      = true" in main
    assert "delete_protection  = true" in main
    assert "rebuild_protection = true" in main
    assert 'image       = "ubuntu-24.04"' in main


def test_secrets_state_and_plan_artifacts_are_not_committed_by_design() -> None:
    readme = (INFRA / "README.md").read_text(encoding="utf-8")
    ignore = (INFRA / ".gitignore").read_text(encoding="utf-8")
    example = (INFRA / "terraform.tfvars.example").read_text(encoding="utf-8")

    assert "HCLOUD_TOKEN" in readme
    assert "HCLOUD_TOKEN" in example
    assert "*.tfstate" in ignore
    assert "*.tfplan" in ignore
    assert "terraform.tfvars" in ignore
    assert "sk_live_" not in example
    assert "whsec_" not in example


def test_powershell_wrapper_plans_by_default_and_never_prints_token() -> None:
    script = (INFRA / "provision.ps1").read_text(encoding="utf-8")

    assert "[switch]$Apply" in script
    assert "$env:HCLOUD_TOKEN" in script
    assert "terraform plan -input=false -out=$PlanFile" in script
    assert "terraform apply -input=false $PlanFile" in script
    assert "terraform init -input=false" in script
    assert "terraform validate -no-color" in script
    assert "if (-not $Apply)" in script
    assert "No infrastructure was changed" in script
    assert "Review the plan with: terraform show veridra.tfplan" in script
    assert "Remove-Item -LiteralPath $PlanFile -Force" in script
    assert "Token detected in process environment (value will not be printed)" in script
    assert "Write-Host $env:HCLOUD_TOKEN" not in script
    assert "terraform.tfvars is missing" in script


def test_tfvars_helper_requires_restricted_cidr_and_reads_public_key() -> None:
    script = (INFRA / "prepare.ps1").read_text(encoding="utf-8")

    assert "[Parameter(Mandatory = $true)]" in script
    assert "[string]$SshCidr" in script
    assert "$HOME\\.ssh\\id_ed25519.pub" in script
    assert "0.0.0.0/0" in script
    assert "::/0" in script
    assert "Refusing an open-to-world SSH CIDR" in script
    assert "Get-Content -LiteralPath $SshPublicKeyPath" in script
    assert "ssh-ed25519" in script
    assert "terraform.tfvars" in script
    assert "HCLOUD_TOKEN" in script
    assert "no HCLOUD_TOKEN is written" in script
