from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.identity_middleware import VerifiedIdentityMiddleware
from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    Tenant,
    TenantMembership,
    TenantRole,
)
from veridra.session_api import router as session_router
from veridra.session_cookie import SecureSessionCookieExtractor
from veridra.session_identity_adapter import ServerSideSessionIdentityAdapter
from veridra.session_lifecycle import SessionLifecycleService
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore

NOW = datetime.now(UTC)
CREDENTIAL = "server-generated-session-credential-value-0001"
SESSION_ID = "server-generated-session-identifier-001"


def _identity_store(tmp_path: Path) -> tuple[SQLiteIdentityRecordStore, Tenant, AuthenticatedUser]:
    store = SQLiteIdentityRecordStore(tmp_path / "identity.sqlite3")
    store.initialize()
    tenant = Tenant.build(slug="session-tenant", display_name="Session tenant", now=NOW)
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
    return store, tenant, user


def _client(store: SQLiteIdentityRecordStore) -> TestClient:
    app = FastAPI()
    app.state.veridra_identity_store = store
    app.add_middleware(
        VerifiedIdentityMiddleware,
        adapter=ServerSideSessionIdentityAdapter(
            extractor=SecureSessionCookieExtractor(),
            store=store,
            clock=lambda: NOW + timedelta(minutes=1),
        ),
    )
    app.include_router(session_router)
    return TestClient(app)


@pytest.mark.asyncio
async def test_service_issues_server_generated_tenant_bound_session(tmp_path: Path) -> None:
    store, tenant, user = _identity_store(tmp_path)
    service = SessionLifecycleService(
        store,
        clock=lambda: NOW,
        credential_factory=lambda: CREDENTIAL,
        session_id_factory=lambda: SESSION_ID,
    )

    issued = service.issue(user_id=user.id, tenant_id=tenant.id, lifetime=timedelta(hours=2))
    records = await store.load_by_credential(CREDENTIAL)

    assert issued.credential == CREDENTIAL
    assert issued.session.id == SESSION_ID
    assert issued.session.expires_at == NOW + timedelta(hours=2)
    assert records is not None
    assert records.tenant.id == tenant.id
    assert records.user.id == user.id


def test_service_rejects_non_positive_lifetime(tmp_path: Path) -> None:
    store, tenant, user = _identity_store(tmp_path)
    service = SessionLifecycleService(store, clock=lambda: NOW)

    with pytest.raises(ValueError, match="positive"):
        service.issue(user_id=user.id, tenant_id=tenant.id, lifetime=timedelta(0))


def test_current_session_returns_verified_server_side_context(tmp_path: Path) -> None:
    store, tenant, user = _identity_store(tmp_path)
    SessionLifecycleService(
        store,
        clock=lambda: NOW,
        credential_factory=lambda: CREDENTIAL,
        session_id_factory=lambda: SESSION_ID,
    ).issue(user_id=user.id, tenant_id=tenant.id)
    client = _client(store)
    client.cookies.set("veridra_session", CREDENTIAL)

    response = client.get("/api/session/current")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": user.id,
        "tenant_id": tenant.id,
        "role": "owner",
        "session_id": SESSION_ID,
        "authenticated_at": NOW.isoformat().replace("+00:00", "Z"),
    }


@pytest.mark.asyncio
async def test_rotation_revokes_old_credential_and_activates_replacement(tmp_path: Path) -> None:
    store, tenant, user = _identity_store(tmp_path)
    SessionLifecycleService(
        store,
        clock=lambda: NOW,
        credential_factory=lambda: CREDENTIAL,
        session_id_factory=lambda: SESSION_ID,
    ).issue(user_id=user.id, tenant_id=tenant.id)
    client = _client(store)
    client.cookies.set("veridra_session", CREDENTIAL)

    response = client.post("/api/session/rotate")
    replacement = response.cookies.get("veridra_session")

    assert response.status_code == 200
    assert replacement is not None and replacement != CREDENTIAL
    assert await store.load_by_credential(CREDENTIAL) is not None
    old_records = await store.load_by_credential(CREDENTIAL)
    assert old_records is not None and old_records.session.status.value == "revoked"

    client.cookies.set("veridra_session", CREDENTIAL)
    assert client.get("/api/session/current").status_code == 401
    client.cookies.set("veridra_session", replacement)
    assert client.get("/api/session/current").status_code == 200


@pytest.mark.asyncio
async def test_failed_rotation_keeps_current_session_active(tmp_path: Path) -> None:
    store, tenant, user = _identity_store(tmp_path)
    service = SessionLifecycleService(
        store,
        clock=lambda: NOW,
        credential_factory=lambda: CREDENTIAL,
        session_id_factory=lambda: SESSION_ID,
    )
    service.issue(user_id=user.id, tenant_id=tenant.id)
    conflicting = SessionLifecycleService(
        store,
        clock=lambda: NOW + timedelta(minutes=1),
        credential_factory=lambda: "replacement-session-credential-value-0001",
        session_id_factory=lambda: SESSION_ID,
    )

    with pytest.raises(sqlite3.IntegrityError):
        conflicting.rotate(
            current_session_id=SESSION_ID,
            user_id=user.id,
            tenant_id=tenant.id,
        )

    records = await store.load_by_credential(CREDENTIAL)
    assert records is not None and records.session.status.value == "active"


def test_logout_revokes_session_and_clears_cookie(tmp_path: Path) -> None:
    store, tenant, user = _identity_store(tmp_path)
    SessionLifecycleService(
        store,
        clock=lambda: NOW,
        credential_factory=lambda: CREDENTIAL,
        session_id_factory=lambda: SESSION_ID,
    ).issue(user_id=user.id, tenant_id=tenant.id)
    client = _client(store)
    client.cookies.set("veridra_session", CREDENTIAL)

    response = client.post("/api/session/logout")

    assert response.status_code == 204
    set_cookie = response.headers["set-cookie"]
    assert "veridra_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert client.post("/api/session/logout").status_code == 401
