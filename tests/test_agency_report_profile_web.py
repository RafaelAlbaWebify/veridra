from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_report_profile_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_profile_store import TenantProfileStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 15, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="agency-profile-owner-001",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="agency-profile-viewer-01",
    authenticated_at=NOW,
)


def _client(tmp_path: Path) -> tuple[TestClient, str, Path]:
    root = tmp_path / "tenants"
    projects = TenantProjectStore(root)
    project_id = projects.save(
        OWNER,
        ClientProject.build(
            name="Client <Site>",
            target_url="https://example.com/",
            client_label="Client Co",
        ),
    )
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "owner":
            bind_verified_request_identity(request, OWNER)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), project_id, root


def test_profile_page_requires_identity_escapes_and_is_read_only(tmp_path: Path) -> None:
    client, project_id, root = _client(tmp_path)
    project_path = root / OWNER.tenant_id / "projects" / f"{project_id}.json"
    before = project_path.read_bytes()

    anonymous = client.get(f"/agency/projects/{project_id}/reports/profile")
    owner = client.get(
        f"/agency/projects/{project_id}/reports/profile",
        headers={"x-test-role": "owner"},
    )

    assert anonymous.status_code == 401
    assert owner.status_code == 200
    assert "Client &lt;Site&gt;" in owner.text
    assert "Client <Site>" not in owner.text
    assert project_path.read_bytes() == before


def test_viewer_cannot_manage_project_profile(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/reports/profile",
        headers={"x-test-role": "viewer"},
    )

    assert response.status_code == 403


def test_create_profile_applies_it_without_rotating_project_id(tmp_path: Path) -> None:
    client, project_id, root = _client(tmp_path)

    response = client.post(
        f"/agency/projects/{project_id}/reports/profile/create",
        headers={"x-test-role": "owner"},
        data={
            "organisation_name": "Agency One",
            "client_name": "Client Co",
            "language": "es",
            "accent_colour": "#123456",
            "show_raw_evidence": "yes",
            "sections": ["executive_summary", "findings", "call_to_action"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/agency/projects/{project_id}/reports?profile=created"
    )
    projects = TenantProjectStore(root)
    project = projects.load(OWNER, projects.ref(OWNER, project_id))
    assert project.profile_id is not None
    profile = TenantProfileStore(root).load(
        OWNER,
        TenantProfileStore.ref(OWNER, project.profile_id),
    )
    assert profile.organisation_name == "Agency One"
    assert profile.language == "es"
    assert profile.section_order == (
        "executive_summary",
        "findings",
        "call_to_action",
    )
    assert len(projects.list(OWNER)) == 1


def test_select_default_profile_preserves_project_identity(tmp_path: Path) -> None:
    client, project_id, root = _client(tmp_path)

    response = client.post(
        f"/agency/projects/{project_id}/reports/profile/select",
        headers={"x-test-role": "owner"},
        data={"profile_id": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    projects = TenantProjectStore(root)
    project = projects.load(OWNER, projects.ref(OWNER, project_id))
    assert project.profile_id is None
    assert len(projects.list(OWNER)) == 1
