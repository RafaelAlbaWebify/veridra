# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra import agency_conversion_web
from veridra.agency_conversion_web import router
from veridra.core import demo_assessment
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

NOW = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)
OWNER_CREDENTIAL = "owner-session-credential-value-00000001"
VIEWER_CREDENTIAL = "viewer-session-credential-value-0000001"


def _active_user(email: str) -> AuthenticatedUser:
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
    owner_tenant = Tenant.build(slug="owner-tenant", display_name="Owner", now=NOW)
    viewer_tenant = Tenant.build(slug="viewer-tenant", display_name="Viewer", now=NOW)
    _save_identity(
        store,
        tenant=owner_tenant,
        user=_active_user("owner@example.com"),
        role=TenantRole.owner,
        credential=OWNER_CREDENTIAL,
        session_id="agency-conversion-owner",
    )
    _save_identity(
        store,
        tenant=viewer_tenant,
        user=_active_user("viewer@example.com"),
        role=TenantRole.viewer,
        credential=VIEWER_CREDENTIAL,
        session_id="agency-conversion-viewer",
    )
    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path / "tenants"
    adapter = ServerSideSessionIdentityAdapter(
        extractor=SecureSessionCookieExtractor(),
        store=store,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    app.add_middleware(VerifiedIdentityMiddleware, adapter=adapter)
    app.include_router(router)
    return TestClient(app), owner_tenant, viewer_tenant


def test_anonymous_confirmation_shows_sign_in_without_persistence(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)

    response = client.get("/agency/convert", params={"url": "https://example.com"})

    assert response.status_code == 200
    assert "Sign in to create a client project" in response.text
    assert not (tmp_path / "tenants").exists()


def test_viewer_sees_permission_message_and_cannot_submit(tmp_path: Path) -> None:
    client, _, viewer_tenant = _client(tmp_path)
    client.cookies.set("veridra_session", VIEWER_CREDENTIAL)

    page = client.get("/agency/convert", params={"url": "https://example.com"})
    submitted = client.post(
        "/agency/convert",
        data={"url": "https://example.com", "project_name": "Forbidden"},
    )

    assert "Project creation is not permitted" in page.text
    assert submitted.status_code == 403
    assert not (tmp_path / "tenants" / viewer_tenant.id).exists()


def test_owner_get_does_not_persist_and_escapes_target(tmp_path: Path) -> None:
    client, owner_tenant, _ = _client(tmp_path)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)

    response = client.get(
        "/agency/convert",
        params={"url": "https://example.com/?q=<script>alert(1)</script>"},
    )

    assert response.status_code == 200
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert not (tmp_path / "tenants" / owner_tenant.id / "projects").exists()


def test_owner_confirms_conversion_and_reaches_tenant_next_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, owner_tenant, _ = _client(tmp_path)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)
    assessment = demo_assessment().model_copy(update={"target": "https://example.com/"})
    monkeypatch.setattr(agency_conversion_web, "assess_url", lambda _url: assessment)

    response = client.post(
        "/agency/convert",
        data={
            "url": "https://example.com",
            "project_name": "<b>Example project</b>",
            "client_label": "Example & Co",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/agency/projects/")
    project_id = location.rsplit("/", 1)[-1]
    project_path = (
        tmp_path / "tenants" / owner_tenant.id / "projects" / f"{project_id}.json"
    )
    assert project_path.exists()

    detail = client.get(location)
    assert detail.status_code == 200
    assert "&lt;b&gt;Example project&lt;/b&gt;" in detail.text
    assert "<b>Example project</b>" not in detail.text
    assert "Create remediation tasks" in detail.text
    assert "Enable monitoring" in detail.text


def test_completed_agency_audit_adds_conversion_only_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _client(tmp_path)
    assessment = demo_assessment().model_copy(update={"target": "https://example.com/"})
    monkeypatch.setattr(agency_conversion_web, "assess_url", lambda _url: assessment)

    response = client.get("/agency/audit", params={"url": "https://example.com"})

    assert response.status_code == 200
    assert "Create client project" in response.text
    assert "/agency/convert?url=https%3A%2F%2Fexample.com%2F" in response.text
