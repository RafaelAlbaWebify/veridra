from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_task_management_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.task_store import RemediationTask, TaskStatus
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_task_store import TenantTaskStore

NOW = datetime(2026, 8, 20, 10, 30, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="agency-task-manage-owner-01",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="agency-task-manage-viewer1",
    authenticated_at=NOW,
)


def _client(tmp_path: Path) -> tuple[TestClient, Path, str, str]:
    root = tmp_path / "tenants"
    project_id = TenantProjectStore(root).save(
        OWNER,
        ClientProject.build(
            name="Example <Client>",
            target_url="https://example.com/",
        ),
    )
    task_id = TenantTaskStore(root).save(
        OWNER,
        RemediationTask(
            project_id=project_id,
            finding_id="finding-1",
            title="Fix <title> metadata",
            source_assessment_id="b" * 24,
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
    return TestClient(app), root, project_id, task_id


def test_task_list_is_tenant_scoped_escaped_and_permissioned(tmp_path: Path) -> None:
    client, _, project_id, task_id = _client(tmp_path)

    owner = client.get(
        f"/agency/projects/{project_id}/tasks",
        headers={"x-test-role": "owner"},
    )
    viewer = client.get(
        f"/agency/projects/{project_id}/tasks",
        headers={"x-test-role": "viewer"},
    )

    assert owner.status_code == 200
    assert viewer.status_code == 403
    assert "Example &lt;Client&gt;" in owner.text
    assert "Example <Client>" not in owner.text
    assert "Fix &lt;title&gt; metadata" in owner.text
    assert f"/agency/projects/{project_id}/tasks/{task_id}" in owner.text
    assert "verification required" in owner.text
    assert "does not mean independently verified" in owner.text


def test_task_list_rejects_unknown_status(tmp_path: Path) -> None:
    client, _, project_id, _ = _client(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/tasks?status=bogus",
        headers={"x-test-role": "owner"},
    )

    assert response.status_code == 400


def test_task_detail_keeps_source_identity_server_side(tmp_path: Path) -> None:
    client, _, project_id, task_id = _client(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/tasks/{task_id}",
        headers={"x-test-role": "owner"},
    )

    assert response.status_code == 200
    assert "Fix &lt;title&gt; metadata" in response.text
    assert "finding-1" in response.text
    assert "b" * 24 in response.text
    assert "name='project_id'" not in response.text
    assert "name='finding_id'" not in response.text
    assert "name='source_assessment_id'" not in response.text
    assert "name='status'" in response.text
    assert "name='owner_label'" in response.text
    assert "name='due_date'" in response.text
    assert "name='notes'" in response.text


def test_task_update_changes_only_work_fields(tmp_path: Path) -> None:
    client, root, project_id, task_id = _client(tmp_path)
    store = TenantTaskStore(root)
    before = store.load(OWNER, store.ref(OWNER, task_id))

    response = client.post(
        f"/agency/projects/{project_id}/tasks/{task_id}",
        headers={"x-test-role": "owner"},
        data={
            "status": "in_progress",
            "owner_label": "Rafael",
            "due_date": "2026-08-25",
            "notes": "Work started.",
            "project_id": "f" * 24,
            "finding_id": "tampered",
            "source_assessment_id": "e" * 24,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/agency/projects/{project_id}/tasks"
    entries = store.list(OWNER, project_id=project_id)
    assert len(entries) == 1
    _, updated = entries[0]
    assert updated.project_id == before.project_id
    assert updated.finding_id == before.finding_id
    assert updated.source_assessment_id == before.source_assessment_id
    assert updated.status == TaskStatus.in_progress
    assert updated.owner_label == "Rafael"
    assert updated.due_date == "2026-08-25"
    assert updated.notes == "Work started."


def test_invalid_task_update_does_not_mutate(tmp_path: Path) -> None:
    client, root, project_id, task_id = _client(tmp_path)
    store = TenantTaskStore(root)
    before = store.list(OWNER, project_id=project_id)

    response = client.post(
        f"/agency/projects/{project_id}/tasks/{task_id}",
        headers={"x-test-role": "owner"},
        data={"status": "automatic_magic_fix"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert store.list(OWNER, project_id=project_id) == before


def test_task_delete_removes_only_selected_project_task(tmp_path: Path) -> None:
    client, root, project_id, task_id = _client(tmp_path)

    response = client.post(
        f"/agency/projects/{project_id}/tasks/{task_id}/delete",
        headers={"x-test-role": "owner"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/agency/projects/{project_id}/tasks"
    assert TenantTaskStore(root).list(OWNER, project_id=project_id) == []
