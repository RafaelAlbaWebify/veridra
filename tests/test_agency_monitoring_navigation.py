from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
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

NOW = datetime(2026, 7, 27, 18, 0, tzinfo=UTC)
ANALYST = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.analyst,
    session_id="monitoring-navigation-analyst",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="monitoring-navigation-viewer-1",
    authenticated_at=NOW,
)


def _client(tmp_path: Path) -> tuple[TestClient, str, str, str]:
    root = tmp_path / "tenants"
    project_id = TenantProjectStore(root).save(
        ANALYST,
        ClientProject.build(name="Monitoring navigation", target_url="https://example.com"),
    )
    history = TenantHistoryStore(root)
    before = history.save(ANALYST, project_id, demo_assessment())
    after = history.save(ANALYST, project_id, demo_assessment())
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.headers.get("x-test-role") == "viewer":
            bind_verified_request_identity(request, VIEWER)
        else:
            bind_verified_request_identity(request, ANALYST)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), project_id, before, after


def test_monitoring_page_has_project_navigation_for_analyst(tmp_path: Path) -> None:
    client, project_id, _, _ = _client(tmp_path)

    response = client.get(f"/agency/projects/{project_id}/monitoring")

    assert response.status_code == 200
    assert "aria-label='Agency navigation'" in response.text
    assert "href='/agency/projects' aria-current='page'" in response.text
    assert f"href='/agency/projects/{project_id}'" in response.text
    assert "href='/agency/leads'" not in response.text
    assert "href='/workspace'" not in response.text


def test_monitoring_page_hides_management_navigation_for_viewer(tmp_path: Path) -> None:
    client, project_id, _, _ = _client(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/monitoring",
        headers={"x-test-role": "viewer"},
    )

    assert response.status_code == 200
    assert "href='/agency/projects' aria-current='page'" in response.text
    assert "href='/agency/leads'" not in response.text
    assert "href='/workspace'" not in response.text
    assert "href='/workspace/members'" not in response.text
    assert "Save monitoring configuration" not in response.text


def test_comparison_page_keeps_project_navigation(tmp_path: Path) -> None:
    client, project_id, before, after = _client(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/monitoring/compare",
        params={"before": before, "after": after},
    )

    assert response.status_code == 200
    assert "aria-label='Agency navigation'" in response.text
    assert "href='/agency/projects' aria-current='page'" in response.text
    assert f"href='/agency/projects/{project_id}'" in response.text
    assert f"href='/agency/projects/{project_id}/monitoring'" in response.text
