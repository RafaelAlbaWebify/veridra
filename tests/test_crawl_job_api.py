from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.crawl_job_api import router
from veridra.crawl_jobs import CrawlJobState, SQLiteCrawlJobStore
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import (
    PlanName,
    UsageKind,
    WorkspaceConfig,
    WorkspaceStatus,
    usage_period,
)

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="crawl-job-api-owner-0001",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="crawl-job-api-viewer-01",
    authenticated_at=NOW,
)
OTHER = RequestIdentity(
    user_id="3" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.owner,
    session_id="crawl-job-api-other-0001",
    authenticated_at=NOW,
)


def _client(
    tmp_path: Path,
    *,
    plan: PlanName = PlanName.free,
    status: WorkspaceStatus = WorkspaceStatus.active,
) -> tuple[TestClient, Path, str, str]:
    root = tmp_path / "tenants"
    policy = TenantWorkspacePolicy(root)
    policy.save(
        OWNER,
        WorkspaceConfig(plan=plan, status=status),
    )
    projects = TenantProjectStore(root)
    first_project_id = projects.save(
        OWNER,
        ClientProject.build(
            name="First project",
            target_url="https://example.com/",
            crawl_profile="quick",
        ),
    )
    second_project_id = projects.save(
        OWNER,
        ClientProject.build(
            name="Second project",
            target_url="https://second.example/",
            crawl_profile="quick",
        ),
    )
    projects.save(
        OTHER,
        ClientProject.build(
            name="Other tenant",
            target_url="https://other.example/",
            crawl_profile="quick",
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
        elif role == "other":
            bind_verified_request_identity(request, OTHER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), root, first_project_id, second_project_id


def _effective(root: Path) -> dict[UsageKind, int]:
    policy = TenantWorkspacePolicy(root)
    workspace = policy.load(OWNER)
    return policy.usage_ledger(OWNER).effective_totals(
        usage_period(workspace, now=NOW),
        now=NOW,
    )


def test_enqueue_reserves_audit_and_project_page_budget(tmp_path: Path) -> None:
    client, root, project_id, _ = _client(tmp_path)

    response = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "owner"},
        json={
            "project_id": project_id,
            "request_key": "manual:2026-10-02T12:00",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["crawl_profile"] == "quick"
    assert payload["page_budget"] == 10
    assert payload["pages_completed"] == 0
    assert payload["state"] == "queued"
    totals = _effective(root)
    assert totals[UsageKind.audit] == 1
    assert totals[UsageKind.crawled_page] == 10
    stored = SQLiteCrawlJobStore(root / "crawl-jobs.sqlite3").load(
        tenant_id=OWNER.tenant_id,
        job_id=payload["id"],
    )
    assert stored.audit_reservation_id
    assert stored.page_reservation_id


def test_duplicate_request_is_idempotent_without_double_reservation(tmp_path: Path) -> None:
    client, root, project_id, _ = _client(tmp_path)
    body = {
        "project_id": project_id,
        "request_key": "manual:same",
    }

    first = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "owner"},
        json=body,
    )
    second = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "owner"},
        json=body,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    totals = _effective(root)
    assert totals[UsageKind.audit] == 1
    assert totals[UsageKind.crawled_page] == 10
    assert len(
        SQLiteCrawlJobStore(root / "crawl-jobs.sqlite3").list_for_tenant(
            OWNER.tenant_id
        )
    ) == 1


def test_plan_concurrency_rejects_second_active_job_and_releases_reservations(
    tmp_path: Path,
) -> None:
    client, root, first_project_id, second_project_id = _client(tmp_path)

    first = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "owner"},
        json={"project_id": first_project_id, "request_key": "manual:1"},
    )
    second = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "owner"},
        json={"project_id": second_project_id, "request_key": "manual:2"},
    )

    assert first.status_code == 201
    assert second.status_code == 429
    assert "concurrency allowance" in second.json()["detail"]
    totals = _effective(root)
    assert totals[UsageKind.audit] == 1
    assert totals[UsageKind.crawled_page] == 10


def test_cancel_releases_usage_reservations(tmp_path: Path) -> None:
    client, root, project_id, _ = _client(tmp_path)
    created = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "owner"},
        json={"project_id": project_id, "request_key": "manual:cancel"},
    )
    job_id = created.json()["id"]

    response = client.delete(
        f"/api/tenant/crawl-jobs/{job_id}",
        headers={"x-test-role": "owner"},
    )

    assert response.status_code == 200
    assert response.json()["state"] == CrawlJobState.cancelled.value
    assert _effective(root).get(UsageKind.audit, 0) == 0
    assert _effective(root).get(UsageKind.crawled_page, 0) == 0


def test_suspended_workspace_cannot_enqueue_and_reserves_nothing(tmp_path: Path) -> None:
    client, root, project_id, _ = _client(
        tmp_path,
        status=WorkspaceStatus.suspended,
    )

    response = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "owner"},
        json={"project_id": project_id, "request_key": "manual:suspended"},
    )

    assert response.status_code == 403
    assert "workspace is suspended" in response.json()["detail"].lower()
    assert _effective(root).get(UsageKind.audit, 0) == 0
    assert _effective(root).get(UsageKind.crawled_page, 0) == 0


def test_viewer_cannot_enqueue_but_can_list(tmp_path: Path) -> None:
    client, _, project_id, _ = _client(tmp_path)

    denied = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "viewer"},
        json={"project_id": project_id, "request_key": "manual:viewer"},
    )
    listed = client.get(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "viewer"},
    )

    assert denied.status_code == 403
    assert listed.status_code == 200
    assert listed.json() == []


def test_other_tenant_cannot_enqueue_owner_project(tmp_path: Path) -> None:
    client, _, project_id, _ = _client(tmp_path)

    response = client.post(
        "/api/tenant/crawl-jobs",
        headers={"x-test-role": "other"},
        json={"project_id": project_id, "request_key": "manual:cross-tenant"},
    )

    assert response.status_code == 404
