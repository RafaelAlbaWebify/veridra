from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from veridra.identity_email_delivery import PasswordResetEmailAdapter
from veridra.runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment
from veridra.runtime_email import configure_runtime_email


def _config(tmp_path: Path, environment: RuntimeEnvironment) -> RuntimeConfig:
    return RuntimeConfig(
        environment=environment,
        identity_database=tmp_path / "identity.sqlite3",
        tenant_data_root=tmp_path / "tenants",
        trusted_origin="https://app.example.com" if environment is RuntimeEnvironment.production else None,
        allowed_hosts=("app.example.com",) if environment is RuntimeEnvironment.production else (),
        trusted_proxy_ips=(),
        max_request_body_bytes=1_000_000,
        bind_host="127.0.0.1",
        bind_port=8000,
    )


def _clear_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "VERIDRA_SMTP_HOST",
        "VERIDRA_SMTP_SENDER",
        "VERIDRA_SMTP_PORT",
        "VERIDRA_SMTP_ENCRYPTION",
        "VERIDRA_SMTP_USERNAME",
        "VERIDRA_SMTP_PASSWORD",
        "VERIDRA_SMTP_PASSWORD_ENV",
    ):
        monkeypatch.delenv(name, raising=False)


def test_development_can_run_without_transactional_email(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_smtp(monkeypatch)
    app = FastAPI()

    configure_runtime_email(app, _config(tmp_path, RuntimeEnvironment.development))

    assert not hasattr(app.state, "veridra_password_reset_delivery")


def test_production_requires_smtp_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_smtp(monkeypatch)

    with pytest.raises(RuntimeConfigurationError, match="required in production"):
        configure_runtime_email(FastAPI(), _config(tmp_path, RuntimeEnvironment.production))


def test_production_requires_auth_secret_when_username_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_smtp(monkeypatch)
    monkeypatch.setenv("VERIDRA_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("VERIDRA_SMTP_SENDER", "security@example.com")
    monkeypatch.setenv("VERIDRA_SMTP_USERNAME", "mailer@example.com")

    with pytest.raises(RuntimeConfigurationError, match="VERIDRA_SMTP_PASSWORD"):
        configure_runtime_email(FastAPI(), _config(tmp_path, RuntimeEnvironment.production))


def test_configured_smtp_installs_password_reset_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_smtp(monkeypatch)
    monkeypatch.setenv("VERIDRA_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("VERIDRA_SMTP_SENDER", "security@example.com")
    app = FastAPI()

    configure_runtime_email(app, _config(tmp_path, RuntimeEnvironment.production))

    assert isinstance(app.state.veridra_password_reset_delivery, PasswordResetEmailAdapter)
    assert app.state.veridra_smtp_config.host == "smtp.example.test"
