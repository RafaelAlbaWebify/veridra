from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "deployment"


def test_compose_keeps_application_private_and_persists_state() -> None:
    compose = (DEPLOYMENT / "compose.yaml").read_text(encoding="utf-8")

    assert '"80:80"' in compose
    assert '"443:443"' in compose
    assert '"8000:8000"' not in compose
    assert "expose:\n      - \"8000\"" in compose
    assert "veridra_data:/var/lib/veridra" in compose
    assert "condition: service_healthy" in compose
    assert "veridra-monitoring-worker" in compose
    assert "profiles:\n      - worker" in compose
    assert 'restart: "no"' in compose


def test_caddy_preserves_runtime_proxy_boundary_and_redacts_tokens() -> None:
    caddyfile = (DEPLOYMENT / "Caddyfile").read_text(encoding="utf-8")

    assert "reverse_proxy web:8000" in caddyfile
    assert "header_up -Forwarded" in caddyfile
    assert "header_up -X-Forwarded-*" in caddyfile
    assert "replace token REDACTED" in caddyfile
    assert "request>remote_ip delete" in caddyfile
    assert "request>client_ip delete" in caddyfile
    assert "health_uri /health/ready" in caddyfile
    assert "Host {$VERIDRA_DOMAIN}" in caddyfile


def test_environment_template_is_safe_and_real_file_is_ignored() -> None:
    example = (DEPLOYMENT / "veridra.env.example").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "VERIDRA_ENV=production" in example
    assert "VERIDRA_IDENTITY_DB=/var/lib/veridra/identity/identity.sqlite3" in example
    assert "VERIDRA_TENANT_DATA_ROOT=/var/lib/veridra/tenants" in example
    assert "VERIDRA_PRIVACY_URL=" in example
    assert "VERIDRA_TERMS_URL=" in example
    assert "VERIDRA_SMTP_HOST=" in example
    assert "sk_live_replace" in example
    assert "deployment/veridra.env" in gitignore
    assert not (DEPLOYMENT / "veridra.env").exists()


def test_systemd_worker_is_bounded_and_non_overlapping() -> None:
    worker_script = (DEPLOYMENT / "worker-run.sh").read_text(encoding="utf-8")
    worker_service = (DEPLOYMENT / "systemd/veridra-worker.service").read_text(
        encoding="utf-8"
    )
    worker_timer = (DEPLOYMENT / "systemd/veridra-worker.timer").read_text(
        encoding="utf-8"
    )

    assert "flock -n" in worker_script
    assert "docker compose" in worker_script
    assert "run --rm worker" in worker_script
    assert "Type=oneshot" in worker_service
    assert "worker-run.sh" in worker_service
    assert "OnUnitActiveSec=15min" in worker_timer
    assert "Persistent=true" in worker_timer


def test_backup_automation_quiesces_writers_and_uses_verified_cli() -> None:
    backup_script = (DEPLOYMENT / "backup-run.sh").read_text(encoding="utf-8")
    backup_service = (DEPLOYMENT / "systemd/veridra-backup.service").read_text(
        encoding="utf-8"
    )
    backup_timer = (DEPLOYMENT / "systemd/veridra-backup.timer").read_text(
        encoding="utf-8"
    )

    assert "flock -n" in backup_script
    assert 'systemctl stop "${WORKER_TIMER}"' in backup_script
    assert "systemctl stop veridra-worker.service" in backup_script
    assert "compose.yaml stop web" in backup_script
    assert "veridra-backup backup" in backup_script
    assert "--confirm-quiesced" in backup_script
    assert "independent off-host storage" in backup_script
    assert "Type=oneshot" in backup_service
    assert "backup-run.sh" in backup_service
    assert "OnCalendar=" in backup_timer
    assert "Persistent=true" in backup_timer


def test_only_one_canonical_deployment_bundle_exists() -> None:
    assert DEPLOYMENT.is_dir()
    assert not (ROOT / "deploy").exists()
