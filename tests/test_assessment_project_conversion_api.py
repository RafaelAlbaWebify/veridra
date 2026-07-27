from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.assessment_project_conversion_api import router
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

NOW = datetime(2026, 7, 27, 1, 0, tzinfo=UTC)
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
        session_id="conversion-owner-session",
    )
    _save_identity(
        store,
        tenant=viewer_tenant,
        user=_active_user("viewer@example.com"),
        role=TenantRole.viewer,
        credential=VIEWER_CREDENTIAL,
        session_id="conversion-viewer-session",
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


def _payload() -> dict[str, object]:
    assessment = demo_assessment().model_copy(update={"target": "https://example.com/"})
    return {
        "assessment": assessment.model_dump(mode="json"),
        "project_name": "Example client",
        "client_label": "Example Ltd",
    }


def test_conversion_requires_verified_identity(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)

    response = client.post("/api/tenant/projects/from-assessment", json=_payload())

    assert response.status_code == 401


def test_owner_converts_assessment_into_project_and_history(tmp_path: Path) -> None:
    client, owner_tenant, _ = _client(tmp_path)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)

    response = client.post("/api/tenant/projects/from-assessment", json=_payload())

    assert response.status_code == 201
    body = response.json()
    project_path = (
        tmp_path
        / "tenants"
        / owner_tenant.id
        / "projects"
        / f"{body['project_id']}.json"
    )
    assessment_path = (
        tmp_path
        / "tenants"
        / owner_tenant.id
        / "projects"
        / body["project_id"]
        / "assessments"
        / f"{body['assessment_id']}.json"
    )
    assert project_path.exists()
    assert assessment_path.exists()
    assert "https://example.com/" in project_path.read_text(encoding="utf-8")


def test_viewer_cannot_convert_and_has_no_tenant_files(tmp_path: Path) -> None:
    client, _, viewer_tenant = _client(tmp_path)
    client.cookies.set("veridra_session", VIEWER_CREDENTIAL)

    response = client.post("/api/tenant/projects/from-assessment", json=_payload())

    assert response.status_code == 403
    assert not (tmp_path / "tenants" / viewer_tenant.id).exists()


def test_target_is_derived_from_assessment_and_extra_target_is_rejected(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)
    payload = _payload()
    payload["target_url"] = "https://attacker.example"

    response = client.post("/api/tenant/projects/from-assessment", json=payload)

    assert response.status_code == 422


def test_missing_tenant_profile_is_generically_concealed(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)
    payload = _payload()
    payload["profile_id"] = "0" * 24

    response = client.post("/api/tenant/projects/from-assessment", json=payload)

    assert response.status_code == 404
    assert response.json() == {"detail": "Report profile not found."}
