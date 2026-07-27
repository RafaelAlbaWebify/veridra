from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_enforcement import enforce_workspace_policy
from veridra.workspace_policy import PlanName, UsageKind, WorkspaceConfig, usage_period

NOW = datetime(2026, 7, 27, 17, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="workspace-enforcement-owner",
    authenticated_at=NOW,
)
OTHER_OWNER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.owner,
    session_id="workspace-enforcement-other",
    authenticated_at=NOW,
)


def _app(root: Path) -> FastAPI:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    app.middleware("http")(enforce_workspace_policy)

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "owner":
            bind_verified_request_identity(request, OWNER)
        elif role == "other-owner":
            bind_verified_request_identity(request, OTHER_OWNER)
        return await call_next(request)

    @app.post("/api/tenant/projects/from-assessment")
    def projects() -> PlainTextResponse:
        return PlainTextResponse("saved")

    @app.post("/api/tenant/report-profiles")
    def profiles() -> PlainTextResponse:
        return PlainTextResponse("saved")

    @app.post("/api/tenant/lead-forms")
    def forms() -> PlainTextResponse:
        return PlainTextResponse("saved")

    @app.post("/agency/projects/{project_id}/monitoring/run")
    def monitoring(project_id: str) -> PlainTextResponse:
        return PlainTextResponse(project_id)

    @app.get("/api/tenant/projects/{project_id}/assessments/{assessment_id}/report.pdf")
    def pdf(project_id: str, assessment_id: str) -> PlainTextResponse:
        return PlainTextResponse(f"{project_id}:{assessment_id}:pdf")

    @app.get("/api/tenant/projects/{project_id}/assessments/{assessment_id}/export")
    def export(project_id: str, assessment_id: str) -> PlainTextResponse:
        return PlainTextResponse(f"{project_id}:{assessment_id}:export")

    @app.get("/free/security")
    def free_tool() -> PlainTextResponse:
        return PlainTextResponse("free")

    return app


def test_unconfigured_tenant_preserves_existing_routes(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path / "tenants"))

    response = client.post(
        "/api/tenant/report-profiles", headers={"x-test-role": "owner"}
    )

    assert response.status_code == 200


def test_free_plan_blocks_features_and_project_overage(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    TenantWorkspacePolicy(root).save(OWNER, WorkspaceConfig(plan=PlanName.free))
    TenantProjectStore(root).save(
        OWNER,
        ClientProject.build(name="One", target_url="https://example.com"),
    )
    client = TestClient(_app(root))
    headers = {"x-test-role": "owner"}

    assert client.post(
        "/api/tenant/projects/from-assessment", headers=headers
    ).status_code == 429
    assert client.post(
        "/api/tenant/report-profiles", headers=headers
    ).status_code == 403
    assert client.post("/api/tenant/lead-forms", headers=headers).status_code == 403


def test_agency_plan_records_successful_tenant_usage(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    policy = TenantWorkspacePolicy(root)
    policy.save(OWNER, WorkspaceConfig(plan=PlanName.agency))
    client = TestClient(_app(root))
    headers = {"x-test-role": "owner"}
    project_id = "p" * 24
    assessment_id = "a" * 24

    assert client.post(
        f"/agency/projects/{project_id}/monitoring/run", headers=headers
    ).status_code == 200
    assert client.get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/report.pdf",
        headers=headers,
    ).status_code == 200
    assert client.get(
        f"/api/tenant/projects/{project_id}/assessments/{assessment_id}/export",
        headers=headers,
    ).status_code == 200

    workspace = policy.load(OWNER)
    totals = policy.usage_ledger(OWNER).totals(usage_period(workspace))
    assert totals[UsageKind.monitoring_run] == 1
    assert totals[UsageKind.pdf] == 1
    assert totals[UsageKind.export] == 1


def test_enforcement_is_tenant_isolated(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    policy = TenantWorkspacePolicy(root)
    policy.save(OWNER, WorkspaceConfig(plan=PlanName.free))
    policy.save(OTHER_OWNER, WorkspaceConfig(plan=PlanName.agency))
    client = TestClient(_app(root))

    first = client.post(
        "/api/tenant/report-profiles", headers={"x-test-role": "owner"}
    )
    second = client.post(
        "/api/tenant/report-profiles", headers={"x-test-role": "other-owner"}
    )

    assert first.status_code == 403
    assert second.status_code == 200


def test_anonymous_and_free_tools_are_not_tenant_metered(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    policy = TenantWorkspacePolicy(root)
    policy.save(OWNER, WorkspaceConfig(plan=PlanName.agency))
    client = TestClient(_app(root))

    assert client.get("/free/security", headers={"x-test-role": "owner"}).status_code == 200
    assert client.post("/api/tenant/report-profiles").status_code == 200
    assert policy.usage_ledger(OWNER).list() == []
