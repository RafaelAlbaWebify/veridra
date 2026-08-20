from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from veridra.runtime_billing import StripeBillingRuntime, configure_runtime_billing
from veridra.runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment


def _runtime(tmp_path: Path) -> RuntimeConfig:
    return RuntimeConfig(
        environment=RuntimeEnvironment.production,
        identity_database=tmp_path / "identity.sqlite3",
        tenant_data_root=tmp_path / "tenants",
        trusted_origin="https://app.example.com",
        allowed_hosts=("app.example.com",),
        trusted_proxy_ips=(),
        max_request_body_bytes=1_000_000,
        bind_host="127.0.0.1",
        bind_port=8000,
    )


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "VERIDRA_STRIPE_SECRET_KEY",
        "VERIDRA_STRIPE_WEBHOOK_SECRET",
        "VERIDRA_STRIPE_PRICE_SOLO",
        "VERIDRA_STRIPE_PRICE_PROFESSIONAL",
        "VERIDRA_STRIPE_PRICE_AGENCY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "https://app.example.com")


def _configure_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERIDRA_STRIPE_SECRET_KEY", "sk_test_secret")
    monkeypatch.setenv("VERIDRA_STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("VERIDRA_STRIPE_PRICE_SOLO", "price_solo")
    monkeypatch.setenv("VERIDRA_STRIPE_PRICE_PROFESSIONAL", "price_professional")
    monkeypatch.setenv("VERIDRA_STRIPE_PRICE_AGENCY", "price_agency")


def test_runtime_does_not_enable_billing_from_trusted_origin_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    app = FastAPI()

    configure_runtime_billing(app, _runtime(tmp_path))

    assert not hasattr(app.state, "veridra_stripe_billing")


def test_partial_stripe_runtime_configuration_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VERIDRA_STRIPE_SECRET_KEY", "sk_test_secret")

    with pytest.raises(RuntimeConfigurationError, match="Stripe billing configuration"):
        configure_runtime_billing(FastAPI(), _runtime(tmp_path))


def test_complete_stripe_configuration_installs_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    _configure_stripe(monkeypatch)
    app = FastAPI()

    configure_runtime_billing(app, _runtime(tmp_path))

    billing = app.state.veridra_stripe_billing
    assert isinstance(billing, StripeBillingRuntime)
    assert billing.config.price_professional == "price_professional"
    assert billing.adapter.tenant_root == tmp_path / "tenants"
