from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.core import demo_assessment
from veridra.finding_task_api import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="owner-finding-task-session-01",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.viewer,
    session_id="viewer-finding-task-session-1",
    authenticated_at=NOW,
)


def _client(tmp_path: Path) -> tuple[TestClient, str, str, str]:
    root = tmp_path / "tenants"
    project = ClientProject.build(name="Client", target_url="https://example.com")
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

    app.include_router(router)
    return TestClient(app), project_id, assessment_id, finding_id


def _payload(project_id: str, assessment_id: str, finding_id: str) -> dict[str, str]:
    return {
        "project_id": project_id,
        "assessment_id": assessment_id,
        "finding_id": finding_id,
    }


def test_finding_task_conversion_requires_identity(tmp_path: Path) -> None:
    client, project_id, assessment_id, finding_id = _client(tmp_path)

    response = client.post(
        "/api/tenant/tasks/from-finding",
        json=_payload(project_id, assessment_id, finding_id),
    )

    assert response.status_code == 401


def test_viewer_cannot_create_finding_task(tmp_path: Path) -> None:
    client, project_id, assessment_id, finding_id = _client(tmp_path)

    response = client.post(
        "/api/tenant/tasks/from-finding",
        headers={"x-test-role": "viewer"},
        json=_payload(project_id, assessment_id, finding_id),
    )

    assert response.status_code == 403


def test_owner_creates_canonical_idempotent_task_from_saved_finding(tmp_path: Path) -> None:
    client, project_id, assessment_id, finding_id = _client(tmp_path)
    payload = _payload(project_id, assessment_id, finding_id)

    first = client.post(
        "/api/tenant/tasks/from-finding",
        headers={"x-test-role": "owner"},
        json=payload,
    )
    second = client.post(
        "/api/tenant/tasks/from-finding",
        headers={"x-test-role": "owner"},
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    task_id = first.json()["task_id"]
    task_path = tmp_path / "tenants" / OWNER.tenant_id / "tasks" / f"{task_id}.json"
    text = task_path.read_text(encoding="utf-8")
    assert finding_id in text
    assert assessment_id in text
    assert "Observation:" in text
    assert "Recommended fix:" in text


def test_missing_finding_is_generically_concealed(tmp_path: Path) -> None:
    client, project_id, assessment_id, _ = _client(tmp_path)

    response = client.post(
        "/api/tenant/tasks/from-finding",
        headers={"x-test-role": "owner"},
        json=_payload(project_id, assessment_id, "missing-finding"),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Finding source not found."}


def test_cross_tenant_project_reference_is_concealed(tmp_path: Path) -> None:
    client, project_id, assessment_id, finding_id = _client(tmp_path)

    response = client.post(
        "/api/tenant/tasks/from-finding",
        headers={"x-test-role": "viewer"},
        json=_payload(project_id, assessment_id, finding_id),
    )

    assert response.status_code == 403
