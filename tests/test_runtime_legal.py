from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from veridra.runtime_config import (
    RuntimeConfig,
    RuntimeConfigurationError,
    RuntimeEnvironment,
)
from veridra.runtime_legal import LegalLinks, configure_runtime_legal


def _runtime(environment: RuntimeEnvironment) -> RuntimeConfig:
    return RuntimeConfig(
        environment=environment,
        identity_database=Path("identity.sqlite3"),
        tenant_data_root=Path("tenants"),
        trusted_origin="https://app.example.com",
        allowed_hosts=("app.example.com",),
        trusted_proxy_ips=(),
        max_request_body_bytes=1_000_000,
        bind_host="127.0.0.1",
        bind_port=8000,
    )


def test_legal_links_require_both_https_urls() -> None:
    with pytest.raises(RuntimeConfigurationError):
        LegalLinks.from_environment({"VERIDRA_PRIVACY_URL": "https://example.com/privacy"})
    with pytest.raises(RuntimeConfigurationError):
        LegalLinks.from_environment(
            {
                "VERIDRA_PRIVACY_URL": "http://example.com/privacy",
                "VERIDRA_TERMS_URL": "https://example.com/terms",
            }
        )


def test_production_requires_legal_links(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERIDRA_PRIVACY_URL", raising=False)
    monkeypatch.delenv("VERIDRA_TERMS_URL", raising=False)

    with pytest.raises(RuntimeConfigurationError):
        configure_runtime_legal(FastAPI(), _runtime(RuntimeEnvironment.production))


def test_configured_links_are_exposed_on_app_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERIDRA_PRIVACY_URL", "https://example.com/privacy")
    monkeypatch.setenv("VERIDRA_TERMS_URL", "https://example.com/terms")
    app = FastAPI()

    configure_runtime_legal(app, _runtime(RuntimeEnvironment.test))

    assert app.state.veridra_legal_links == LegalLinks(
        privacy_url="https://example.com/privacy",
        terms_url="https://example.com/terms",
    )
