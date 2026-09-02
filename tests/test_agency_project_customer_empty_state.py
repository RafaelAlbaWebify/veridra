from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_project_customer_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject, ProjectStore
from veridra.request_security import bind_verified_request_identity

NOW = datetime(2026, 9, 2, 16, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="project-customer-empty-owner",
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
        bind_verified_request_identity(request, OWNER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), root


def test_new_project_suppresses_evidence_tools_until_first_assessment(
    tmp_path: Path,
) -> None:
    client, root = _client(tmp_path)
    project_id = ProjectStore(root / OWNER.tenant_id / "projects").save(
        ClientProject.build(
            name="Fresh delivery",
            target_url="https://example.com",
            client_label="Synthetic client",
        )
    )

    response = client.get(f"/agency/projects/{project_id}")

    assert response.status_code == 200
    assert "Saved assessment:</strong> Not available" in response.text
    assert "Run first assessment" in response.text
    assert "Progress / Changes and AI review become available" in response.text
    assert f"/agency/projects/{project_id}/progress" not in response.text
    assert f"/agency/projects/{project_id}/ai-review" not in response.text
    assert "Prepare branded report" not in response.text
