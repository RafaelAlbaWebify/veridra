from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from veridra.operations_api import router as operations_router
from veridra.runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment


def test_development_defaults_remain_local() -> None:
    config = RuntimeConfig.from_environment({})

    assert config.environment is RuntimeEnvironment.development
    assert config.identity_database is None
    assert config.tenant_data_root is None
    assert config.bind_host == "127.0.0.1"
    assert config.bind_port == 8000


def test_production_requires_complete_safe_configuration(tmp_path: Path) -> None:
    with pytest.raises(RuntimeConfigurationError, match="IDENTITY_DB"):
        RuntimeConfig.from_environment({"VERIDRA_ENV": "production"})

    with pytest.raises(RuntimeConfigurationError, match="HTTPS origin"):
        RuntimeConfig.from_environment(
            {
                "VERIDRA_ENV": "production",
                "VERIDRA_IDENTITY_DB": str(tmp_path / "identity.sqlite3"),
                "VERIDRA_TENANT_DATA_ROOT": str(tmp_path / "tenants"),
                "VERIDRA_TRUSTED_ORIGIN": "http://app.example.com",
                "VERIDRA_ALLOWED_HOSTS": "app.example.com",
            }
        )


def test_valid_production_configuration_is_explicit(tmp_path: Path) -> None:
    config = RuntimeConfig.from_environment(
        {
            "VERIDRA_ENV": "production",
            "VERIDRA_IDENTITY_DB": str(tmp_path / "identity.sqlite3"),
            "VERIDRA_TENANT_DATA_ROOT": str(tmp_path / "tenants"),
            "VERIDRA_TRUSTED_ORIGIN": "https://app.example.com",
            "VERIDRA_ALLOWED_HOSTS": "app.example.com",
            "VERIDRA_BIND_HOST": "0.0.0.0",
            "VERIDRA_BIND_PORT": "8443",
        }
    )

    assert config.environment is RuntimeEnvironment.production
    assert config.allowed_hosts == ("app.example.com",)
    assert config.bind_host == "0.0.0.0"
    assert config.bind_port == 8443


def test_health_is_non_disclosing_and_readiness_checks_dependencies(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(operations_router)
    app.state.veridra_tenant_data_root = tmp_path / "missing"
    client = TestClient(app)

    health = client.get("/health")
    unavailable = client.get("/ready")
    app.state.veridra_tenant_data_root.mkdir()
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert unavailable.status_code == 503
    assert unavailable.json() == {"status": "unavailable"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_trusted_host_rejects_unconfigured_host() -> None:
    app = FastAPI()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["app.example.com"])
    app.include_router(operations_router)
    client = TestClient(app, base_url="https://app.example.com")

    assert client.get("/health").status_code == 200
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
