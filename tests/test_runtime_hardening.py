from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from veridra.operations_api import router as operations_router
from veridra.runtime_boundary import RuntimeBoundaryMiddleware
from veridra.runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment


def test_development_defaults_remain_local() -> None:
    config = RuntimeConfig.from_environment({})

    assert config.environment is RuntimeEnvironment.development
    assert config.identity_database is None
    assert config.tenant_data_root is None
    assert config.bind_host == "127.0.0.1"
    assert config.bind_port == 8000
    assert config.trusted_proxy_ips == ()
    assert config.max_request_body_bytes == 1_000_000


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
            "VERIDRA_TRUSTED_PROXY_IPS": "127.0.0.1,10.0.0.8",
            "VERIDRA_MAX_REQUEST_BODY_BYTES": "2000000",
            "VERIDRA_BIND_HOST": "0.0.0.0",
            "VERIDRA_BIND_PORT": "8443",
        }
    )

    assert config.environment is RuntimeEnvironment.production
    assert config.allowed_hosts == ("app.example.com",)
    assert config.trusted_proxy_ips == ("127.0.0.1", "10.0.0.8")
    assert config.max_request_body_bytes == 2_000_000
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


def _boundary_client(*, trusted_proxy_ips: tuple[str, ...] = ()) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RuntimeBoundaryMiddleware,
        max_body_bytes=32,
        trusted_proxy_ips=trusted_proxy_ips,
    )

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, str]:
        return {"body": (await request.body()).decode()}

    return TestClient(app)


def test_oversized_mutation_body_is_rejected_before_route_parsing() -> None:
    client = _boundary_client()

    accepted = client.post("/echo", content="a" * 32)
    rejected = client.post("/echo", content="a" * 33)

    assert accepted.status_code == 200
    assert rejected.status_code == 413
    assert rejected.json() == {"detail": "Request body too large."}


def test_untrusted_forwarded_headers_are_rejected() -> None:
    client = _boundary_client()

    response = client.post(
        "/echo",
        content="ok",
        headers={"x-forwarded-host": "evil.example"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Untrusted forwarded headers."}


def test_trusted_proxy_headers_do_not_redefine_request_identity() -> None:
    client = _boundary_client(trusted_proxy_ips=("testclient",))

    response = client.post(
        "/echo",
        content="ok",
        headers={
            "x-forwarded-host": "public.example",
            "x-forwarded-proto": "https",
            "x-forwarded-for": "203.0.113.7",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"body": "ok"}
