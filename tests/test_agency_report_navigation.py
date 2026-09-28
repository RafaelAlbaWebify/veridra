from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_report_web import router
from veridra.core import demo_assessment
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 17, 0, tzinfo=UTC)
ANALYST = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.analyst,
    session_id="report-navigation-analyst-01",
    authenticated_at=NOW,
)


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    root = tmp_path / "tenants"
    project_id = TenantProjectStore(root).save(
        ANALYST,
        ClientProject.build(name="Navigation report", target_url="https://example.com"),
    )
    TenantHistoryStore(root).save(ANALYST, project_id, demo_assessment())
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, ANALYST)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), project_id


def test_report_hub_has_project_navigation_and_breadcrumbs(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    response = client.get(f"/agency/projects/{project_id}/reports")

    assert response.status_code == 200
    assert "aria-label='Agency navigation'" in response.text
    assert "href='/agency/projects' aria-current='page'" in response.text
    assert f"href='/agency/projects/{project_id}'" in response.text
    assert "Project overview" in response.text
    assert "href='/agency/leads'" not in response.text
    assert "href='/workspace'" not in response.text
    assert "href='/workspace/members'" not in response.text


def test_report_delivery_confirmation_keeps_shared_navigation(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    response = client.get(f"/agency/projects/{project_id}/reports/send")

    assert response.status_code == 200
    assert "aria-label='Agency navigation'" in response.text
    assert "href='/agency/projects' aria-current='page'" in response.text
    assert f"href='/agency/projects/{project_id}'" in response.text
    assert f"href='/agency/projects/{project_id}/reports'" in response.text
    assert "No email is sent by opening this page" in response.text
