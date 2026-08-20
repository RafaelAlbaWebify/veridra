from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.health_web import router
from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.runtime_config import RuntimeConfig, RuntimeEnvironment


def _runtime(
    tmp_path: Path,
    *,
    environment: RuntimeEnvironment,
) -> RuntimeConfig:
    return RuntimeConfig(
        environment=environment,
        identity_database=tmp_path / "identity" / "identity.sqlite3",
        tenant_data_root=tmp_path / "tenants",
        trusted_origin=(
            "https://app.example.com"
            if environment is RuntimeEnvironment.production
            else None
        ),
        allowed_hosts=(
            ("app.example.com",)
            if environment is RuntimeEnvironment.production
            else ()
        ),
        trusted_proxy_ips=(),
        max_request_body_bytes=1_000_000,
        bind_host="127.0.0.1",
        bind_port=8000,
    )


def _client(runtime: RuntimeConfig | None) -> TestClient:
    app = FastAPI()
    if runtime is not None:
        app.state.veridra_runtime_config = runtime
    app.include_router(router)
    return TestClient(app)


def test_liveness_does_not_claim_dependency_readiness(tmp_path: Path) -> None:
    client = _client(_runtime(tmp_path, environment=RuntimeEnvironment.production))

    live = client.get("/health/live")
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready"}
    assert live.headers["cache-control"] == "no-store"
    assert ready.headers["cache-control"] == "no-store"


def test_readiness_requires_runtime_configuration() -> None:
    response = _client(None).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_development_readiness_does_not_require_production_persistence(tmp_path: Path) -> None:
    response = _client(
        _runtime(tmp_path, environment=RuntimeEnvironment.development)
    ).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_readiness_requires_bootstrapped_identity_and_tenant_root(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path, environment=RuntimeEnvironment.production)
    assert runtime.identity_database is not None
    assert runtime.tenant_data_root is not None
    runtime.configure_directories()
    SQLiteIdentityBootstrap(
        runtime.identity_database,
        tenant_data_root=runtime.tenant_data_root,
    ).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password="owner-correct-horse-battery",
        confirmation=BOOTSTRAP_CONFIRMATION,
    )

    response = _client(runtime).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_readiness_does_not_leak_database_failure_detail(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, environment=RuntimeEnvironment.production)
    assert runtime.identity_database is not None
    assert runtime.tenant_data_root is not None
    runtime.configure_directories()
    runtime.identity_database.write_text("not a sqlite database", encoding="utf-8")

    response = _client(runtime).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert str(runtime.identity_database) not in response.text
