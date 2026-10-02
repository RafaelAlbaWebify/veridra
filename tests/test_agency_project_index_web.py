from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_project_index_web import router
from veridra.agency_workflow_web import router as workflow_router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 22, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="agency-project-index-owner",
    authenticated_at=NOW,
)
SALES = RequestIdentity(
    user_id="3" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.sales,
    session_id="agency-project-index-sales",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="4" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="agency-project-index-viewer",
    authenticated_at=NOW,
)
OTHER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.owner,
    session_id="agency-project-index-other",
    authenticated_at=NOW,
)


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path]:
    monkeypatch.setenv("VERIDRA_ENV", "operator")
    root = tmp_path / "tenants"
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-identity")
        identities = {"owner": OWNER, "sales": SALES, "viewer": VIEWER, "other": OTHER}
        if role in identities:
            bind_verified_request_identity(request, identities[role])
        return await call_next(request)

    app.include_router(workflow_router)
    app.include_router(router)
    return TestClient(app), root


def test_project_index_requires_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/agency/projects")
    assert response.status_code == 401


def test_empty_project_index_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, root = _client(tmp_path, monkeypatch)
    response = client.get("/agency/projects", headers={"x-test-identity": "owner"})
    assert response.status_code == 200
    assert "No delivery projects exist yet" in response.text
    assert not (root / OWNER.tenant_id).exists()


def test_project_index_navigation_is_role_aware(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    owner = client.get("/agency/projects", headers={"x-test-identity": "owner"})
    assert "aria-current='page'" in owner.text
    assert "href='/agency/leads'" not in owner.text
    assert "href='/workspace'" not in owner.text
    assert "href='/workspace/members'" not in owner.text
    assert "href='/agency/prospects'" in owner.text

    sales = client.get("/agency/projects", headers={"x-test-identity": "sales"})
    assert "href='/agency/leads'" not in sales.text
    assert "href='/workspace'" not in sales.text
    assert "href='/workspace/members'" not in sales.text
    assert "href='/agency/prospects'" in sales.text

    viewer = client.get("/agency/projects", headers={"x-test-identity": "viewer"})
    assert "href='/agency/leads'" not in viewer.text
    assert "href='/workspace'" not in viewer.text
    assert "href='/workspace/members'" not in viewer.text
    assert "href='/agency/projects'" in viewer.text


def test_project_index_is_tenant_isolated_and_escaped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, root = _client(tmp_path, monkeypatch)
    store = TenantProjectStore(root)
    project_id = store.save(
        OWNER,
        ClientProject.build(
            name="<script>Client project</script>",
            target_url="https://example.com",
            client_label="A & B",
            crawl_profile="standard",
        ),
    )
    store.save(
        OTHER,
        ClientProject.build(
            name="Other tenant project",
            target_url="https://other.example",
        ),
    )

    response = client.get("/agency/projects", headers={"x-test-identity": "owner"})

    assert response.status_code == 200
    assert "&lt;script&gt;Client project&lt;/script&gt;" in response.text
    assert "<script>Client project</script>" not in response.text
    assert "A &amp; B" in response.text
    assert "Other tenant project" not in response.text
    assert f"/agency/projects/{project_id}" in response.text
    assert f"/agency/projects/{project_id}/reports" not in response.text
    assert f"/agency/projects/{project_id}/monitoring" not in response.text
    assert "Standard" in response.text


def test_agency_home_advertises_authoritative_project_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/agency", headers={"x-test-identity": "owner"})
    assert response.status_code == 200
    assert "href='/agency/projects'" in response.text
    assert "href='/projects'" not in response.text
    assert "href='/monitoring'" not in response.text


def test_hosted_project_index_uses_saas_project_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("VERIDRA_ENV", "production")

    response = client.get(
        "/agency/projects",
        headers={"x-test-identity": "owner"},
    )

    assert response.status_code == 200
    assert "No client projects exist yet." in response.text
    assert "Run a website audit or convert a qualified inbound lead" in response.text
    assert "Client projects keep website assessments" in response.text
    assert "work-start gate" not in response.text
    assert "Presence Care" not in response.text
