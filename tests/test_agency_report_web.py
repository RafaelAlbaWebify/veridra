# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_conversion_web import router as project_router
from veridra.agency_report_web import router as report_router
from veridra.core import demo_assessment
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.report_profiles import ReportProfile
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_profile_store import TenantProfileStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
ANALYST = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.analyst,
    session_id="analyst-report-hub-session-01",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="viewer-report-hub-session-001",
    authenticated_at=NOW,
)
OTHER_ANALYST = RequestIdentity(
    user_id="3" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.analyst,
    session_id="other-report-hub-session-0001",
    authenticated_at=NOW,
)


def _client(root: Path) -> TestClient:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "analyst":
            bind_verified_request_identity(request, ANALYST)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        elif role == "other":
            bind_verified_request_identity(request, OTHER_ANALYST)
        return await call_next(request)

    app.include_router(project_router)
    app.include_router(report_router)
    return TestClient(app)


def _project(
    tmp_path: Path,
    *,
    profile: ReportProfile | None = None,
    assessment: bool = True,
) -> tuple[TestClient, str, str | None]:
    root = tmp_path / "tenants"
    profile_id = TenantProfileStore(root).save(ANALYST, profile) if profile else None
    project = ClientProject.build(
        name="Report <Client>",
        target_url="https://example.com",
        client_label="Client & Co",
        profile_id=profile_id,
    )
    project_id = TenantProjectStore(root).save(ANALYST, project)
    assessment_id = None
    if assessment:
        saved = demo_assessment().model_copy(update={"target": "https://example.com/"})
        assessment_id = TenantHistoryStore(root).save(ANALYST, project_id, saved)
    return _client(root), project_id, assessment_id


def test_report_hub_requires_identity(tmp_path: Path) -> None:
    client, project_id, _ = _project(tmp_path)

    response = client.get(f"/agency/projects/{project_id}/reports")

    assert response.status_code == 401


def test_viewer_cannot_open_report_hub(tmp_path: Path) -> None:
    client, project_id, _ = _project(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/reports",
        headers={"x-test-role": "viewer"},
    )

    assert response.status_code == 403


def test_default_profile_hub_is_read_only_and_links_tenant_outputs(tmp_path: Path) -> None:
    client, project_id, assessment_id = _project(tmp_path)
    project_path = tmp_path / "tenants" / ANALYST.tenant_id / "projects" / f"{project_id}.json"
    before = project_path.read_bytes()

    response = client.get(
        f"/agency/projects/{project_id}/reports",
        headers={"x-test-role": "analyst"},
    )

    assert response.status_code == 200
    assert "Reports for Report &lt;Client&gt;" in response.text
    assert "Default Veridra profile" in response.text
    assert "Client &amp; Co" in response.text
    assert assessment_id is not None
    base = f"/api/tenant/projects/{project_id}/assessments/{assessment_id}"
    assert f"href='{base}/report'" in response.text
    assert f"href='{base}/report.pdf'" in response.text
    assert f"href='{base}/export'" in response.text
    assert project_path.read_bytes() == before


def test_tenant_profile_content_is_shown_and_escaped(tmp_path: Path) -> None:
    profile = ReportProfile(
        organisation_name="Agency <Brand>",
        client_name="Client > Name",
        language="es",
        accent_colour="#123456",
        call_to_action_label="Book & review",
        call_to_action_url="https://agency.example/contact?x=1&y=2",
    )
    client, project_id, _ = _project(tmp_path, profile=profile)

    response = client.get(
        f"/agency/projects/{project_id}/reports",
        headers={"x-test-role": "analyst"},
    )

    assert response.status_code == 200
    assert "Tenant report profile" in response.text
    assert "Agency &lt;Brand&gt;" in response.text
    assert "Client &gt; Name" in response.text
    assert "Book &amp; review" in response.text
    assert "x=1&amp;y=2" in response.text
    assert "#123456" in response.text


def test_report_hub_shows_no_assessment_state(tmp_path: Path) -> None:
    client, project_id, assessment_id = _project(tmp_path, assessment=False)

    response = client.get(
        f"/agency/projects/{project_id}/reports",
        headers={"x-test-role": "analyst"},
    )

    assert assessment_id is None
    assert response.status_code == 200
    assert "No saved assessment is available." in response.text
    assert "Preview branded HTML" not in response.text
    assert "Download PDF" not in response.text


def test_cross_tenant_report_hub_is_concealed(tmp_path: Path) -> None:
    client, project_id, _ = _project(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/reports",
        headers={"x-test-role": "other"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Report source not found."}


def test_project_page_links_report_hub_not_legacy_report_screen(tmp_path: Path) -> None:
    client, project_id, _ = _project(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}",
        headers={"x-test-role": "analyst"},
    )

    assert response.status_code == 200
    assert f"href='/agency/projects/{project_id}/reports'" in response.text
    assert "Prepare branded report" in response.text
    assert "href='/report?" not in response.text
