from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import PlanName, UsageEvent, UsageKind, WorkspaceConfig
from veridra.workspace_web import router

NOW = datetime(2026, 7, 27, 16, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="workspace-owner-session-001",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="workspace-viewer-session-01",
    authenticated_at=NOW,
)
OTHER_OWNER = RequestIdentity(
    user_id="3" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.owner,
    session_id="workspace-other-owner-01",
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
        role = request.headers.get("x-test-role")
        if role == "owner":
            bind_verified_request_identity(request, OWNER)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        elif role == "other-owner":
            bind_verified_request_identity(request, OTHER_OWNER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), root


def test_workspace_requires_identity_and_defaults_to_free(tmp_path: Path) -> None:
    client, root = _client(tmp_path)

    anonymous = client.get("/workspace")
    viewer = client.get("/workspace", headers={"x-test-role": "viewer"})

    assert anonymous.status_code == 401
    assert viewer.status_code == 200
    assert "Plan:</strong> Free" in viewer.text
    assert "not payment collection" in viewer.text
    assert "Preview or apply" not in viewer.text
    assert not (root / OWNER.tenant_id / "workspace" / "workspace.json").exists()


def test_owner_can_preview_and_apply_tenant_plan_with_audit(tmp_path: Path) -> None:
    client, root = _client(tmp_path)

    preview = client.get(
        "/workspace/plan-preview?plan=professional&cycle_anchor_day=15",
        headers={"x-test-role": "owner"},
    )
    applied = client.post(
        "/workspace/plan",
        headers={"x-test-role": "owner"},
        data={"plan": "professional", "cycle_anchor_day": "15"},
        follow_redirects=False,
    )

    assert preview.status_code == 200
    assert "does not charge a payment method" in preview.text
    assert applied.status_code == 303
    policy = TenantWorkspacePolicy(root)
    workspace = policy.load(OWNER)
    assert workspace.plan == PlanName.professional
    assert workspace.cycle_anchor_day == 15
    changes = policy.list_plan_changes(OWNER)
    assert len(changes) == 1
    assert changes[0][1].actor_user_id == OWNER.user_id
    assert changes[0][1].previous_plan == PlanName.free
    assert changes[0][1].new_plan == PlanName.professional


def test_viewer_cannot_preview_or_apply_plan(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    preview = client.get(
        "/workspace/plan-preview?plan=agency&cycle_anchor_day=1",
        headers={"x-test-role": "viewer"},
    )
    applied = client.post(
        "/workspace/plan",
        headers={"x-test-role": "viewer"},
        data={"plan": "agency", "cycle_anchor_day": "1"},
    )

    assert preview.status_code == 403
    assert applied.status_code == 403


def test_workspace_and_usage_are_tenant_isolated(tmp_path: Path) -> None:
    client, root = _client(tmp_path)
    policy = TenantWorkspacePolicy(root)
    policy.save(OWNER, WorkspaceConfig(plan=PlanName.solo))
    policy.save(OTHER_OWNER, WorkspaceConfig(plan=PlanName.agency))
    policy.record_usage(
        OWNER,
        UsageEvent(
            kind=UsageKind.audit,
            quantity=2,
            occurred_at=datetime.now(UTC),
            related_id="tenant-a-assessment",
            note="tenant A",
        ),
    )
    policy.record_usage(
        OTHER_OWNER,
        UsageEvent(
            kind=UsageKind.audit,
            quantity=7,
            occurred_at=datetime.now(UTC),
            related_id="tenant-b-assessment",
            note="tenant B",
        ),
    )

    first = client.get("/workspace", headers={"x-test-role": "viewer"})
    first_csv = client.get("/workspace/usage.csv", headers={"x-test-role": "viewer"})
    second = client.get("/workspace", headers={"x-test-role": "other-owner"})
    second_csv = client.get(
        "/workspace/usage.csv", headers={"x-test-role": "other-owner"}
    )

    assert "Plan:</strong> Solo" in first.text
    assert "tenant-a-assessment" in first_csv.text
    assert "tenant-b-assessment" not in first_csv.text
    assert "Plan:</strong> Agency" in second.text
    assert "tenant-b-assessment" in second_csv.text
    assert "tenant-a-assessment" not in second_csv.text
