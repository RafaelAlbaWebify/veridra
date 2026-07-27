# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_conversion_web import router as project_router
from veridra.agency_task_web import router as task_router
from veridra.core import demo_assessment
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="owner-agency-task-session-001",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="viewer-agency-task-session-01",
    authenticated_at=NOW,
)


def _client(tmp_path: Path) -> tuple[TestClient, str, str, str]:
    root = tmp_path / "tenants"
    project = ClientProject.build(name="Example <Client>", target_url="https://example.com")
    project_id = TenantProjectStore(root).save(OWNER, project)
    assessment = demo_assessment().model_copy(update={"target": "https://example.com/"})
    assessment_id = TenantHistoryStore(root).save(OWNER, project_id, assessment)
    finding_id = assessment.findings[0].id

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

    app.include_router(project_router)
    app.include_router(task_router)
    return TestClient(app), project_id, assessment_id, finding_id


def test_saved_findings_requires_identity(tmp_path: Path) -> None:
    client, project_id, assessment_id, _ = _client(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/assessments/{assessment_id}/findings"
    )

    assert response.status_code == 401


def test_saved_findings_get_does_not_create_tasks_and_escapes_project(tmp_path: Path) -> None:
    client, project_id, assessment_id, _ = _client(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/assessments/{assessment_id}/findings",
        headers={"x-test-role": "owner"},
    )

    assert response.status_code == 200
    assert "Example &lt;Client&gt;" in response.text
    assert "Example <Client>" not in response.text
    assert "Create task" in response.text
    assert not (tmp_path / "tenants" / OWNER.tenant_id / "tasks").exists()


def test_viewer_can_review_but_not_open_confirmation(tmp_path: Path) -> None:
    client, project_id, assessment_id, finding_id = _client(tmp_path)

    listing = client.get(
        f"/agency/projects/{project_id}/assessments/{assessment_id}/findings",
        headers={"x-test-role": "viewer"},
    )
    confirmation = client.get(
        "/agency/tasks/from-finding",
        headers={"x-test-role": "viewer"},
        params={
            "project_id": project_id,
            "assessment_id": assessment_id,
            "finding_id": finding_id,
        },
    )

    assert listing.status_code == 200
    assert "Task permission required" in listing.text
    assert confirmation.status_code == 403


def test_owner_confirms_task_and_project_shows_status(tmp_path: Path) -> None:
    client, project_id, assessment_id, finding_id = _client(tmp_path)

    confirmation = client.get(
        "/agency/tasks/from-finding",
        headers={"x-test-role": "owner"},
        params={
            "project_id": project_id,
            "assessment_id": assessment_id,
            "finding_id": finding_id,
        },
    )
    created = client.post(
        "/agency/tasks/from-finding",
        headers={"x-test-role": "owner"},
        data={
            "project_id": project_id,
            "assessment_id": assessment_id,
            "finding_id": finding_id,
        },
        follow_redirects=False,
    )

    assert confirmation.status_code == 200
    assert "Confirm task creation" in confirmation.text
    assert created.status_code == 303
    assert created.headers["location"].startswith(f"/agency/projects/{project_id}?task_created=")
    task_id = created.headers["location"].split("task_created=", 1)[1]
    project_page = client.get(created.headers["location"], headers={"x-test-role": "owner"})
    listing = client.get(
        f"/agency/projects/{project_id}/assessments/{assessment_id}/findings",
        headers={"x-test-role": "owner"},
    )
    assert project_page.status_code == 200
    assert f"Remediation task created:</strong> {task_id}" in project_page.text
    assert f"Task {task_id}" in listing.text


def test_repeated_confirmation_is_idempotent(tmp_path: Path) -> None:
    client, project_id, assessment_id, finding_id = _client(tmp_path)
    data = {
        "project_id": project_id,
        "assessment_id": assessment_id,
        "finding_id": finding_id,
    }

    first = client.post(
        "/agency/tasks/from-finding",
        headers={"x-test-role": "owner"},
        data=data,
        follow_redirects=False,
    )
    second = client.post(
        "/agency/tasks/from-finding",
        headers={"x-test-role": "owner"},
        data=data,
        follow_redirects=False,
    )

    assert first.headers["location"] == second.headers["location"]
