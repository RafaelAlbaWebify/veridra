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
from veridra.password_auth import SQLitePasswordAuthenticator, hash_password, verify_password
from veridra.session_api import router as session_router
from veridra.session_cookie import SecureSessionCookieExtractor
from veridra.session_identity_adapter import ServerSideSessionIdentityAdapter
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore

NOW = datetime(2026, 7, 24, 20, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery-staple"


def _client(
    tmp_path: Path,
    *,
    active_membership: bool = True,
) -> tuple[TestClient, AuthenticatedUser, Tenant]:
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
            active=active_membership,
            created_at=NOW,
        )
    )
    authenticator.set_password(user.id, PASSWORD, updated_at=NOW)
    app = FastAPI()
    app.state.veridra_identity_store = store
    app.state.veridra_password_authenticator = authenticator
    app.add_middleware(
        VerifiedIdentityMiddleware,
        adapter=ServerSideSessionIdentityAdapter(
            extractor=SecureSessionCookieExtractor(),
            store=store,
            clock=lambda: NOW,
        ),
    )
    app.include_router(auth_router)
    app.include_router(session_router)
    return TestClient(app, base_url="https://testserver"), user, tenant


def test_scrypt_hash_uses_salt_and_verifies() -> None:
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    assert first != second
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong-password-value", first)
    assert not verify_password(PASSWORD, "malformed")


def test_login_sets_secure_cookie_and_creates_verified_session(tmp_path: Path) -> None:
    client, user, tenant = _client(tmp_path)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "OWNER@EXAMPLE.COM",
            "tenant_slug": "customer-one",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": user.id,
        "tenant_id": tenant.id,
        "role": "owner",
    }
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    current = client.get("/api/session/current")
    assert current.status_code == 200
    assert current.json()["user_id"] == user.id
    assert current.json()["tenant_id"] == tenant.id


def test_login_failures_use_same_generic_response(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    attempts = [
        {"email": "owner@example.com", "tenant_slug": "customer-one", "password": "wrong"},
        {"email": "missing@example.com", "tenant_slug": "customer-one", "password": PASSWORD},
        {"email": "owner@example.com", "tenant_slug": "another-tenant", "password": PASSWORD},
    ]

    for payload in attempts:
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid login credentials."}


def test_inactive_membership_cannot_login(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path, active_membership=False)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "owner@example.com",
            "tenant_slug": "customer-one",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid login credentials."}
