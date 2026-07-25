from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.core import Assessment, Finding, Status
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.report_profiles import ReportProfile
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_profile_store import TenantProfileStore
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_report_api import router

NOW = datetime(2026, 7, 26, 0, 0, tzinfo=UTC)


def _identity(tenant_id: str, role: TenantRole) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _assessment() -> Assessment:
    return Assessment.build(
        "https://example.com",
        [
            Finding(
                id="security.hsts",
                area="Security posture",
                title="Enable HSTS",
                status=Status.attention,
                severity="medium",
                summary="HSTS is missing.",
                recommendation="Enable HSTS.",
            )
        ],
        generated_at=NOW,
    )


def _client(root: Path, identity: RequestIdentity) -> TestClient:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def _sources(root: Path, identity: RequestIdentity) -> tuple[str, str]:
    profile_id = TenantProfileStore(root).save(
        identity,
        ReportProfile(organisation_name="Tenant Agency"),
    )
    project_id = TenantProjectStore(root).save(
        identity,
        ClientProject.build(
            name="Tenant project",
            target_url="https://example.com",
            profile_id=profile_id,
        ),
    )
    assessment_id = TenantHistoryStore(root).save(
        identity,
        project_id,
        _assessment(),
    )
    return project_id, assessment_id


def test_html_and_export_use_tenant_sources_only(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    identity = _identity("1" * 24, TenantRole.analyst)
    project_id, assessment_id = _sources(root, identity)
    client = _client(root, identity)
    base = f"/api/tenant/projects/{project_id}/assessments/{assessment_id}"

    report = client.get(f"{base}/report")
    export = client.get(f"{base}/export")

    assert report.status_code == 200
    assert "Tenant Agency" in report.text
    assert "Enable HSTS" in report.text
    assert export.status_code == 200
    assert export.headers["content-type"] == "application/zip"
    assert export.content.startswith(b"PK")
    assert not (tmp_path / "history").exists()
    assert not (tmp_path / "profiles").exists()
    assert not (tmp_path / "projects").exists()


def test_viewer_cannot_generate_reports(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    analyst = _identity("2" * 24, TenantRole.analyst)
    viewer = _identity("2" * 24, TenantRole.viewer)
    project_id, assessment_id = _sources(root, analyst)

    response = _client(root, viewer).get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/report"
    )

    assert response.status_code == 403


def test_other_tenant_cannot_discover_report_sources(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    owner = _identity("3" * 24, TenantRole.analyst)
    outsider = _identity("4" * 24, TenantRole.analyst)
    project_id, assessment_id = _sources(root, owner)

    response = _client(root, outsider).get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/report"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Report source not found."}
