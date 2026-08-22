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
