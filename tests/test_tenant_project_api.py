from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.identity_middleware import VerifiedIdentityMiddleware
from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    AuthSession,
    Tenant,
    TenantMembership,
    TenantRole,
)
from veridra.session_cookie import SecureSessionCookieExtractor
from veridra.session_identity_adapter import ServerSideSessionIdentityAdapter
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.tenant_project_api import build_tenant_project_router

NOW = datetime(2026, 7, 24, 20, 0, tzinfo=UTC)
OWNER_CREDENTIAL = "owner-session-credential-value-00000001"
VIEWER_CREDENTIAL = "viewer-session-credential-value-0000001"


def _active_user(*, email: str) -> AuthenticatedUser:
    return AuthenticatedUser.build(email=email, display_name=email, now=NOW).model_copy(
        update={"status": AccountStatus.active, "email_verified_at": NOW}
    )


def _save_identity(
    store: SQLiteIdentityRecordStore,
    *,
    tenant: Tenant,
    user: AuthenticatedUser,
    role: TenantRole,
    credential: str,
    session_id: str,
) -> None:
    store.save_tenant(tenant)
    store.save_user(user)
    store.save_membership(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=role,
            created_at=NOW,
        )
    )
    store.save_session(
        credential=credential,
        tenant_id=tenant.id,
        session=AuthSession(
            id=session_id,
            user_id=user.id,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=8),
        ),
    )


def _client(tmp_path: Path) -> tuple[TestClient, Tenant, Tenant]:
    store = SQLiteIdentityRecordStore(tmp_path / "identity.sqlite3")
    store.initialize()
    owner_tenant = Tenant.build(slug="owner-tenant", display_name="Owner tenant", now=NOW)
    viewer_tenant = Tenant.build(slug="viewer-tenant", display_name="Viewer tenant", now=NOW)
    _save_identity(
        store,
        tenant=owner_tenant,
        user=_active_user(email="owner@example.com"),
        role=TenantRole.owner,
        credential=OWNER_CREDENTIAL,
        session_id="session-tenant-project-api-owner",
    )
    _save_identity(
        store,
        tenant=viewer_tenant,
        user=_active_user(email="viewer@example.com"),
        role=TenantRole.viewer,
        credential=VIEWER_CREDENTIAL,
        session_id="session-tenant-project-api-viewer",
    )

    app = FastAPI()
    adapter = ServerSideSessionIdentityAdapter(
        extractor=SecureSessionCookieExtractor(),
        store=store,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    app.add_middleware(VerifiedIdentityMiddleware, adapter=adapter)
    app.include_router(build_tenant_project_router(root=tmp_path / "tenants"))
    return TestClient(app), owner_tenant, viewer_tenant


def test_project_api_requires_verified_cookie_identity(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)

    response = client.get("/api/tenant/projects")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication is required."}


def test_owner_can_create_list_load_and_delete_project(tmp_path: Path) -> None:
    client, owner_tenant, _ = _client(tmp_path)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)

    created = client.post(
        "/api/tenant/projects",
        json={"name": "Customer site", "target_url": "https://example.com"},
    )
    project_id = created.json()["id"]

    assert created.status_code == 201
    assert client.get("/api/tenant/projects").json()[0]["id"] == project_id
    assert client.get(f"/api/tenant/projects/{project_id}").json()["name"] == "Customer site"
    assert (
        tmp_path / "tenants" / owner_tenant.id / "projects" / f"{project_id}.json"
    ).exists()
    assert client.delete(f"/api/tenant/projects/{project_id}").status_code == 204
    assert client.get("/api/tenant/projects").json() == []


def test_viewer_is_read_only_and_tenant_isolated(tmp_path: Path) -> None:
    client, owner_tenant, viewer_tenant = _client(tmp_path)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)
    created = client.post(
        "/api/tenant/projects",
        json={"name": "Owner project", "target_url": "https://example.com"},
    )
    project_id = created.json()["id"]

    client.cookies.set("veridra_session", VIEWER_CREDENTIAL)

    assert client.get("/api/tenant/projects").json() == []
    assert client.post(
        "/api/tenant/projects",
        json={"name": "Forbidden", "target_url": "https://example.org"},
    ).status_code == 403
    assert client.delete(f"/api/tenant/projects/{project_id}").status_code == 403
    assert not (
        tmp_path / "tenants" / viewer_tenant.id / "projects" / f"{project_id}.json"
    ).exists()
    assert (
        tmp_path / "tenants" / owner_tenant.id / "projects" / f"{project_id}.json"
    ).exists()
