from __future__ import annotations

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

NOW = datetime(2026, 7, 24, 20, 0, tzinfo=UTC)
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


def test_logout_revokes_session_and_clears_cookie(tmp_path: Path) -> None:
    store, tenant, user = _identity_store(tmp_path)
    SessionLifecycleService(
        store,
        clock=lambda: NOW,
        credential_factory=lambda: CREDENTIAL,
        session_id_factory=lambda: SESSION_ID,
    ).issue(user_id=user.id, tenant_id=tenant.id)

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
    client = TestClient(app)
    client.cookies.set("veridra_session", CREDENTIAL)

    response = client.post("/api/session/logout")

    assert response.status_code == 204
    set_cookie = response.headers["set-cookie"]
    assert "veridra_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert client.post("/api/session/logout").status_code == 401
