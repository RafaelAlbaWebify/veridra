# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_monitoring_web import router
from veridra.core import demo_assessment
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 11, 0, tzinfo=UTC)
ANALYST = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.analyst,
    session_id="analyst-comparison-session-01",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="viewer-comparison-session-001",
    authenticated_at=NOW,
)
OTHER_VIEWER = RequestIdentity(
    user_id="3" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.viewer,
    session_id="other-comparison-session-0001",
    authenticated_at=NOW,
)


def _app(root: Path) -> TestClient:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        elif role == "other":
            bind_verified_request_identity(request, OTHER_VIEWER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def _project_with_history(tmp_path: Path, *, count: int) -> tuple[TestClient, str, list[str]]:
    root = tmp_path / "tenants"
    project = ClientProject.build(
        name="Comparison <Client>",
        target_url="https://example.com",
    )
    project_id = TenantProjectStore(root).save(ANALYST, project)
    history = TenantHistoryStore(root)
    identifiers: list[str] = []
    for offset in range(count):
        assessment = demo_assessment().model_copy(
            update={
                "target": "https://example.com/",
                "generated_at": NOW + timedelta(minutes=offset),
            }
        )
        identifiers.append(history.save(ANALYST, project_id, assessment))
    return _app(root), project_id, identifiers


def test_monitoring_page_links_latest_and_previous_assessments(tmp_path: Path) -> None:
    client, project_id, identifiers = _project_with_history(tmp_path, count=2)

    response = client.get(
        f"/agency/projects/{project_id}/monitoring",
        headers={"x-test-role": "viewer"},
    )

    assert response.status_code == 200
    assert "Comparison &lt;Client&gt;" in response.text
    assert "Compare latest assessments" in response.text
    assert f"before={identifiers[0]}" in response.text
    assert f"after={identifiers[1]}" in response.text


def test_viewer_opens_read_only_comparison(tmp_path: Path) -> None:
    client, project_id, identifiers = _project_with_history(tmp_path, count=2)
    root = tmp_path / "tenants" / ANALYST.tenant_id / "projects" / project_id / "assessments"
    before_files = {path.name: path.read_bytes() for path in root.glob("*.json")}

    response = client.get(
        f"/agency/projects/{project_id}/monitoring/compare",
        headers={"x-test-role": "viewer"},
        params={"before": identifiers[0], "after": identifiers[1]},
    )

    assert response.status_code == 200
    assert "Assessment comparison for Comparison &lt;Client&gt;" in response.text
    assert "Added" in response.text
    assert "Resolved" in response.text
    assert "Changed" in response.text
    assert "Unchanged" in response.text
    assert "not client-facing proof of remediation" in response.text
    assert {path.name: path.read_bytes() for path in root.glob("*.json")} == before_files


def test_monitoring_page_shows_insufficient_history_state(tmp_path: Path) -> None:
    client, project_id, _ = _project_with_history(tmp_path, count=1)

    response = client.get(
        f"/agency/projects/{project_id}/monitoring",
        headers={"x-test-role": "viewer"},
    )

    assert response.status_code == 200
    assert "At least two saved assessments are required for comparison." in response.text
    assert "Compare latest assessments" not in response.text


def test_cross_tenant_comparison_is_concealed(tmp_path: Path) -> None:
    client, project_id, identifiers = _project_with_history(tmp_path, count=2)

    response = client.get(
        f"/agency/projects/{project_id}/monitoring/compare",
        headers={"x-test-role": "other"},
        params={"before": identifiers[0], "after": identifiers[1]},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}
