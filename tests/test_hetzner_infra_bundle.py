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


def test_secrets_and_terraform_state_are_not_committed_by_design() -> None:
    readme = (INFRA / "README.md").read_text(encoding="utf-8")
    ignore = (INFRA / ".gitignore").read_text(encoding="utf-8")
    example = (INFRA / "terraform.tfvars.example").read_text(encoding="utf-8")

    assert "HCLOUD_TOKEN" in readme
    assert "HCLOUD_TOKEN" in example
    assert "*.tfstate" in ignore
    assert "terraform.tfvars" in ignore
    assert "sk_live_" not in example
    assert "whsec_" not in example
