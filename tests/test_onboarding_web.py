from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.identity_tenancy import RequestIdentity
from veridra.onboarding_web import router
from veridra.password_auth import SQLitePasswordAuthenticator
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import PlanName

ORIGIN = "https://veridra.example"
PASSWORD = "correct-horse-battery-staple"


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path, Path]:
    database = tmp_path / "identity.sqlite3"
    tenant_root = tmp_path / "tenants"
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    authenticator = SQLitePasswordAuthenticator(database)
    authenticator.initialize()
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_identity_store = store
    app.state.veridra_tenant_data_root = tenant_root
    app.include_router(router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    return TestClient(app), database, tenant_root


def _payload() -> dict[str, str]:
    return {
        "tenant_name": "Example Agency",
        "tenant_slug": "example-agency",
        "owner_name": "Agency Owner",
        "owner_email": "owner@example.com",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
    }


def test_empty_database_exposes_onboarding_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database, tenant_root = _client(tmp_path, monkeypatch)

    response = client.get("/onboarding")

    assert response.status_code == 200
    assert "Create your Veridra agency workspace" in response.text
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0
    assert not tenant_root.exists()


def test_onboarding_requires_trusted_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database, _ = _client(tmp_path, monkeypatch)

    response = client.post(
        "/onboarding",
        data=_payload(),
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0


def test_password_mismatch_creates_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database, tenant_root = _client(tmp_path, monkeypatch)
    payload = _payload()
    payload["password_confirm"] = "different-password-value"

    response = client.post("/onboarding", data=payload, headers={"Origin": ORIGIN})

    assert response.status_code == 400
    assert "Passwords do not match" in response.text
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert not tenant_root.exists()


def test_success_creates_free_owner_session_and_disables_onboarding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database, tenant_root = _client(tmp_path, monkeypatch)

    response = client.post(
        "/onboarding",
        data=_payload(),
        headers={"Origin": ORIGIN},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/agency"
    assert "set-cookie" in response.headers
    records = SQLitePasswordAuthenticator(database).authenticate(
        email="owner@example.com",
        tenant_slug="example-agency",
        password=PASSWORD,
    )
    assert records is not None
    identity = RequestIdentity(
        user_id=records.user.id,
        tenant_id=records.tenant.id,
        membership_role=records.membership.role,
        session_id="onboarding-test-session-01",
        authenticated_at=datetime.now(UTC),
    )
    assert TenantWorkspacePolicy(tenant_root).load(identity).plan == PlanName.free
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1

    replay_get = client.get("/onboarding")
    replay_post = client.post("/onboarding", data=_payload(), headers={"Origin": ORIGIN})
    assert replay_get.status_code == 404
    assert replay_post.status_code == 404
