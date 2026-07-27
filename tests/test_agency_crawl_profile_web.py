from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from veridra import tenant_monitoring_api, tenant_monitoring_execution
from veridra.agency_crawl_profile_web import router
from veridra.core import Assessment, demo_assessment
from veridra.crawl_profiles import CrawlProfile, CrawlProfileName
from veridra.identity_middleware import VerifiedIdentityMiddleware
from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    AuthSession,
    RequestIdentity,
    Tenant,
    TenantMembership,
    TenantRole,
)
from veridra.project_store import ClientProject
from veridra.session_cookie import SecureSessionCookieExtractor
from veridra.session_identity_adapter import ServerSideSessionIdentityAdapter
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 19, 0, tzinfo=UTC)
OWNER_CREDENTIAL = "crawl-profile-owner-session-000001"
VIEWER_CREDENTIAL = "crawl-profile-viewer-session-00001"


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


def _client(tmp_path: Path) -> tuple[TestClient, RequestIdentity, RequestIdentity, Path]:
    store = SQLiteIdentityRecordStore(tmp_path / "identity.sqlite3")
    store.initialize()
    tenant = Tenant.build(slug="crawl-profile-tenant", display_name="Crawl Profile", now=NOW)
    owner = _active_user("owner@example.com")
    viewer = _active_user("viewer@example.com")
    _save_identity(
        store,
        tenant=tenant,
        user=owner,
        role=TenantRole.owner,
        credential=OWNER_CREDENTIAL,
        session_id="crawl-profile-owner-session",
    )
    _save_identity(
        store,
        tenant=tenant,
        user=viewer,
        role=TenantRole.viewer,
        credential=VIEWER_CREDENTIAL,
        session_id="crawl-profile-viewer-session",
    )
    root = tmp_path / "tenants"
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    adapter = ServerSideSessionIdentityAdapter(
        extractor=SecureSessionCookieExtractor(),
        store=store,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    app.add_middleware(VerifiedIdentityMiddleware, adapter=adapter)
    app.include_router(router)
    owner_identity = RequestIdentity(
        user_id=owner.id,
        tenant_id=tenant.id,
        membership_role=TenantRole.owner,
        session_id="crawl-profile-owner-session",
        authenticated_at=NOW,
    )
    viewer_identity = RequestIdentity(
        user_id=viewer.id,
        tenant_id=tenant.id,
        membership_role=TenantRole.viewer,
        session_id="crawl-profile-viewer-session",
        authenticated_at=NOW,
    )
    return TestClient(app), owner_identity, viewer_identity, root


def _save_project(root: Path, identity: RequestIdentity, profile: str = "deep") -> str:
    return TenantProjectStore(root).save(
        identity,
        ClientProject.build(
            name="Profile project",
            target_url="https://example.com",
            crawl_profile=profile,
        ),
    )


def test_owner_can_change_named_profile_without_changing_project_id(tmp_path: Path) -> None:
    client, owner, _, root = _client(tmp_path)
    project_id = _save_project(root, owner)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)

    page = client.get(f"/agency/projects/{project_id}/crawl-profile")
    response = client.post(
        f"/agency/projects/{project_id}/crawl-profile",
        data={"crawl_profile": "standard"},
        follow_redirects=False,
    )

    assert page.status_code == 200
    assert "Deep" in page.text
    assert "Effective pages:</strong> 100" in page.text
    assert "Sitemap URLs:</strong> 1000" in page.text
    assert response.status_code == 303
    assert response.headers["location"].startswith(
        f"/agency/projects/{project_id}/crawl-profile?"
    )
    stored = TenantProjectStore(root).load(
        owner,
        TenantProjectStore(root).ref(owner, project_id),
    )
    assert stored.crawl_profile is CrawlProfileName.standard
    assert stored.resolved_crawl_profile().limits.max_pages == 25


def test_viewer_can_inspect_but_cannot_change_profile(tmp_path: Path) -> None:
    client, owner, viewer, root = _client(tmp_path)
    project_id = _save_project(root, owner)
    client.cookies.set("veridra_session", VIEWER_CREDENTIAL)

    page = client.get(f"/agency/projects/{project_id}/crawl-profile")
    response = client.post(
        f"/agency/projects/{project_id}/crawl-profile",
        data={"crawl_profile": "quick"},
    )

    assert page.status_code == 200
    assert "cannot change it" in page.text
    assert "Save crawl profile" not in page.text
    assert response.status_code == 403
    stored = TenantProjectStore(root).load(
        viewer,
        TenantProjectStore(root).ref(viewer, project_id),
    )
    assert stored.crawl_profile is CrawlProfileName.deep


def test_custom_and_unknown_browser_values_are_rejected(tmp_path: Path) -> None:
    client, owner, _, root = _client(tmp_path)
    project_id = _save_project(root, owner)
    client.cookies.set("veridra_session", OWNER_CREDENTIAL)

    custom = client.post(
        f"/agency/projects/{project_id}/crawl-profile",
        data={"crawl_profile": "custom"},
    )
    unknown = client.post(
        f"/agency/projects/{project_id}/crawl-profile",
        data={"crawl_profile": "unbounded"},
    )

    assert custom.status_code == 400
    assert unknown.status_code == 400


def _request(root: Path) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "app": app,
        }
    )


def test_manual_and_worker_monitoring_use_the_saved_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, owner, _, root = _client(tmp_path)
    project_id = _save_project(root, owner, "standard")
    captured: list[CrawlProfile] = []

    def fake_assess(
        _url: str,
        *,
        crawl_profile: CrawlProfile,
    ) -> Assessment:
        captured.append(crawl_profile)
        return demo_assessment()

    monkeypatch.setattr(tenant_monitoring_api, "assess_url", fake_assess)
    monkeypatch.setattr(tenant_monitoring_execution, "assess_url", fake_assess)

    tenant_monitoring_api.run_monitoring_assessment(
        project_id,
        _request(root),
        owner,
    )
    tenant_monitoring_execution.execute_tenant_monitoring(
        root=root,
        tenant_id=owner.tenant_id,
        project_id=project_id,
    )

    assert [profile.name for profile in captured] == [
        CrawlProfileName.standard,
        CrawlProfileName.standard,
    ]
    assert all(profile.limits.max_pages == 25 for profile in captured)
