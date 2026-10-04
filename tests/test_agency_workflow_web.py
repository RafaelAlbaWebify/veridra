from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_workflow_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.runtime_config import RuntimeConfig, RuntimeEnvironment
from veridra.tenant_project_store import TenantProjectStore
from veridra.workspace_policy import (
    PLAN_CATALOGUE,
    PlanName,
    UsageEvent,
    UsageKind,
    UsageLedger,
    WorkspaceConfig,
    WorkspaceStore,
)

OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="operator-home-test-session",
    authenticated_at=datetime(2026, 9, 30, tzinfo=UTC),
)


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    environment: str = "operator",
) -> TestClient:
    monkeypatch.setenv("VERIDRA_ENV", environment)
    app = FastAPI()

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, OWNER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def _hosted_plan_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    plan: PlanName,
    exhaust_audits: bool = False,
    fill_projects: bool = False,
) -> TestClient:
    monkeypatch.setenv("VERIDRA_ENV", "production")
    root = tmp_path / "tenants"
    workspace_directory = root / OWNER.tenant_id / "workspace"
    WorkspaceStore(workspace_directory).save(
        WorkspaceConfig(plan=plan)
    )
    if exhaust_audits:
        UsageLedger(workspace_directory).record(
            UsageEvent(
                kind=UsageKind.audit,
                quantity=PLAN_CATALOGUE[plan].monthly_audits,
                occurred_at=datetime.now(UTC),
                related_id="home-quota-test",
                note="Exhaust hosted home audit allowance",
            )
        )
    if fill_projects:
        projects = TenantProjectStore(root)
        for index in range(PLAN_CATALOGUE[plan].max_projects):
            projects.save(
                OWNER,
                ClientProject.build(
                    name=f"Capacity project {index + 1}",
                    target_url=f"https://project-{index + 1}.example",
                ),
            )
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    app.state.veridra_runtime_config = RuntimeConfig(
        environment=RuntimeEnvironment.production,
        identity_database=tmp_path / "identity.sqlite3",
        tenant_data_root=root,
        trusted_origin="https://app.example.com",
        allowed_hosts=("app.example.com",),
        trusted_proxy_ips=(),
        max_request_body_bytes=1_000_000,
        bind_host="0.0.0.0",
        bind_port=8443,
    )

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, OWNER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def test_operator_home_explains_current_webify_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).get("/agency")

    assert response.status_code == 200
    assert "VERIDRA operator" in response.text
    assert "1. Discover" in response.text
    assert "2. Qualify" in response.text
    assert "3. Audit" in response.text
    assert "4. Win work" in response.text
    assert "5. Prove" in response.text
    assert "Prospect discovery" in response.text
    assert "Quick audit" in response.text
    assert "Sales / proposals" in response.text
    assert "Customers" in response.text
    assert "Client projects" in response.text
    assert "Presence Care" in response.text
    assert "href='/agency/prospects/discover'" in response.text


def test_operator_home_does_not_expose_saas_or_inbound_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).get("/agency")

    assert response.status_code == 200
    for forbidden in (
        "href='/agency/leads'",
        "href='/agency/lead-forms'",
        "href='/workspace'",
        "href='/workspace/members'",
        "Plan and usage",
        "Team",
        "Inbound leads",
        "Lead forms",
    ):
        assert forbidden not in response.text


def test_quick_audit_handoff_redirects_to_temporary_agency_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).get(
        "/agency/quick-audit",
        params={"target": "  https://example.com/path?a=1&b=2  "},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/agency/audit?url=https%3A%2F%2Fexample.com%2Fpath%3Fa%3D1%26b%3D2"
    )


def test_hosted_home_uses_agency_product_copy_and_exposes_hosted_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch, environment="production").get("/agency")

    assert response.status_code == 200
    assert "VERIDRA agency workspace" in response.text
    assert "Agency workspace" in response.text
    assert "Webify operator" not in response.text
    assert "Operator rule:" not in response.text
    assert "Audit websites, deliver branded evidence" in response.text
    assert "Run a website audit" in response.text
    assert "Projects and reports" in response.text
    assert "Reports & monitoring" in response.text
    assert "Evidence boundary:" in response.text
    assert "href='/agency/leads'" in response.text
    assert "href='/agency/lead-forms'" in response.text
    assert "href='/agency/projects'" in response.text
    assert "href='/workspace'" in response.text
    assert "href='/billing'" in response.text
    assert "href='/workspace/members'" in response.text
    assert "Inbound leads" in response.text
    assert "Lead forms" in response.text
    assert "Billing" in response.text


def test_hosted_free_home_shows_locked_commercial_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _hosted_plan_client(
        tmp_path,
        monkeypatch,
        plan=PlanName.free,
    ).get("/agency")

    assert response.status_code == 200
    assert "White-label branding unlocks on Professional." in response.text
    assert "Recurring monitoring is locked on the active plan." in response.text
    assert "Lead forms · locked" in response.text
    assert "Embedded audit forms require the Agency plan." in response.text
    assert "href='/billing'><strong>Lead forms · locked" in response.text


def test_hosted_agency_home_exposes_full_commercial_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _hosted_plan_client(
        tmp_path,
        monkeypatch,
        plan=PlanName.agency,
    ).get("/agency")

    assert response.status_code == 200
    assert "Create branded white-label reports." in response.text
    assert "Recurring monitoring is available on the active plan." in response.text
    assert "href='/agency/lead-forms'><strong>Lead forms</strong>" in response.text
    assert "Lead forms · locked" not in response.text


def test_hosted_home_locks_quick_audit_when_monthly_allowance_is_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _hosted_plan_client(
        tmp_path,
        monkeypatch,
        plan=PlanName.free,
        exhaust_audits=True,
    ).get("/agency")

    assert response.status_code == 200
    assert "Audit allowance unavailable." in response.text
    assert "monthly audit allowance is exhausted" in response.text
    assert "action='/agency/quick-audit'" not in response.text
    assert "Review plan & usage" in response.text


def test_hosted_home_reports_project_capacity_exhaustion_before_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _hosted_plan_client(
        tmp_path,
        monkeypatch,
        plan=PlanName.free,
        fill_projects=True,
    ).get("/agency")

    assert response.status_code == 200
    assert "Project capacity is exhausted or the workspace is suspended." in response.text
    assert "Existing projects remain available" in response.text


def test_webify_local_agency_home_combines_sales_inbound_and_delivery_without_saas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_LOCAL_AGENCY", "1")
    response = _client(monkeypatch, environment="production").get("/agency")

    assert response.status_code == 200
    assert "WEBIFY · VERIDRA LOCAL" in response.text
    assert "There is no VERIDRA subscription" in response.text
    assert "Sales, website audits and client delivery in one workspace" in response.text
    assert "aria-label='Webify workflow'" in response.text
    for step in ("Find", "Qualify", "Audit", "Deliver", "Prove"):
        assert f"<strong>{step}</strong>" in response.text
    assert "Inbound leads" in response.text
    assert "Lead forms" in response.text
    assert "Customers" in response.text
    assert "Client projects" in response.text
    assert "Presence Care" in response.text
    assert "href='/agency/prospects/discover'" in response.text
    assert "href='/agency/leads'" in response.text
    assert "href='/agency/lead-forms'" in response.text
    assert "href='/workspace'" not in response.text
    assert "href='/billing'" not in response.text
    assert "Plan & usage" not in response.text
    assert "Webify operating areas" not in response.text
    assert "class='local-grid'" in response.text
    assert "class='boundary-line'" in response.text
