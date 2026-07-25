from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.auth_api import router as auth_router
from veridra.identity_middleware import VerifiedIdentityMiddleware
from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    Tenant,
    TenantMembership,
    TenantRole,
)
from veridra.password_auth import SQLitePasswordAuthenticator
from veridra.session_api import router as session_router
from veridra.session_cookie import SecureSessionCookieExtractor
from veridra.session_identity_adapter import ServerSideSessionIdentityAdapter
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore

NOW = datetime(2026, 7, 25, 8, 0, tzinfo=UTC)
OLD_PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "new-correct-horse-battery-staple"


def _client(tmp_path: Path) -> TestClient:
    database = tmp_path / "identity.sqlite3"
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    authenticator = SQLitePasswordAuthenticator(database)
    authenticator.initialize()
    tenant = Tenant.build(slug="customer-one", display_name="Customer one", now=NOW)
    user = AuthenticatedUser.build(
        email="owner@example.com",
        display_name="Owner",
        now=NOW,
    ).model_copy(update={"status": AccountStatus.active, "email_verified_at": NOW})
    store.save_tenant(tenant)
    store.save_user(user)
    store.save_membership(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=TenantRole.owner,
            created_at=NOW,
        )
    )
    authenticator.set_password(user.id, OLD_PASSWORD, updated_at=NOW)
    app = FastAPI()
    app.state.veridra_identity_store = store
    app.state.veridra_password_authenticator = authenticator
    app.add_middleware(
        VerifiedIdentityMiddleware,
        adapter=ServerSideSessionIdentityAdapter(
            extractor=SecureSessionCookieExtractor(),
            store=store,
        ),
    )
    app.include_router(auth_router)
    app.include_router(session_router)
    return TestClient(app, base_url="https://testserver")


def _login(client: TestClient, password: str) -> int:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "owner@example.com",
            "tenant_slug": "customer-one",
            "password": password,
        },
    )
    return int(response.status_code)


def test_password_change_revokes_sessions_and_requires_new_password(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert _login(client, OLD_PASSWORD) == 200
    assert client.get("/api/session/current").status_code == 200

    changed = client.post(
        "/api/auth/password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert changed.status_code == 204
    assert "veridra_session=" in changed.headers["set-cookie"]
    assert client.get("/api/session/current").status_code == 401
    assert _login(client, OLD_PASSWORD) == 401
    assert _login(client, NEW_PASSWORD) == 200
    assert client.get("/api/session/current").status_code == 200


def test_wrong_current_password_preserves_password_and_session(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert _login(client, OLD_PASSWORD) == 200

    response = client.post(
        "/api/auth/password",
        json={"current_password": "wrong-current-password", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Current password is invalid."}
    assert client.get("/api/session/current").status_code == 200
    client.cookies.clear()
    assert _login(client, OLD_PASSWORD) == 200
    assert _login(client, NEW_PASSWORD) == 401
