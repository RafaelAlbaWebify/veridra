from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_conversion_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject, ProjectStore
from veridra.request_security import bind_verified_request_identity

NOW = datetime(2026, 7, 27, 16, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="project-overview-owner-01",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.viewer,
    session_id="project-overview-viewer-1",
    authenticated_at=NOW,
)


def _client(tmp_path: Path) -> tuple[TestClient, Path]:
    root = tmp_path / "tenants"
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-identity")
        if role == "owner":
            bind_verified_request_identity(request, OWNER)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), root


def _project(root: Path, identity: RequestIdentity, name: str) -> str:
    return ProjectStore(root / identity.tenant_id / "projects").save(
        ClientProject.build(name=name, target_url="https://example.com")
    )


def test_owner_project_overview_has_authorized_navigation(tmp_path: Path) -> None:
    client, root = _client(tmp_path)
    project_id = _project(root, OWNER, "Owner project")

    response = client.get(
        f"/agency/projects/{project_id}",
        headers={"x-test-identity": "owner"},
    )

    assert response.status_code == 200
    assert "aria-label='Agency navigation'" in response.text
    assert "href='/agency/projects' aria-current='page'" in response.text
    assert "href='/agency/leads'" in response.text
    assert "href='/workspace'" in response.text
    assert "href='/workspace/members'" in response.text
    assert "<a href='/agency/projects'>Client projects</a>" in response.text


def test_project_without_saved_assessment_recommends_first_assessment_only(
    tmp_path: Path,
) -> None:
    client, root = _client(tmp_path)
    project_id = _project(root, OWNER, "Empty project")

    response = client.get(
        f"/agency/projects/{project_id}",
        headers={"x-test-identity": "owner"},
    )

    assert response.status_code == 200
    assert "Saved assessment:</strong> Not available" in response.text
    assert "Run first assessment" in response.text
    assert "Run the first assessment from Monitoring." in response.text
    assert "Reports, findings and remediation become available" in response.text
    assert "Review saved findings" not in response.text
    assert "Prepare branded report" not in response.text
    assert "Review the saved evidence" not in response.text
    assert "href='/?" not in response.text


def test_viewer_project_overview_hides_unavailable_navigation(tmp_path: Path) -> None:
    client, root = _client(tmp_path)
    project_id = _project(root, VIEWER, "Viewer project")

    response = client.get(
        f"/agency/projects/{project_id}",
        headers={"x-test-identity": "viewer"},
    )

    assert response.status_code == 200
    assert "href='/agency'" in response.text
    assert "href='/agency/projects' aria-current='page'" in response.text
    assert "href='/agency/leads'" not in response.text
    assert "href='/workspace'" not in response.text
    assert "href='/workspace/members'" not in response.text
