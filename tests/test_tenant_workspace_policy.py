from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantRole,
)
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import (
    PlanName,
    UsageEvent,
    UsageKind,
    WorkspaceConfig,
)

NOW = datetime(2026, 7, 27, 16, 0, tzinfo=UTC)
OWNER_A = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="tenant-workspace-owner-a1",
    authenticated_at=NOW,
)
OWNER_B = RequestIdentity(
    user_id="2" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.owner,
    session_id="tenant-workspace-owner-b1",
    authenticated_at=NOW,
)
VIEWER_A = RequestIdentity(
    user_id="3" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="tenant-workspace-viewer1",
    authenticated_at=NOW,
)


def test_missing_tenant_workspace_defaults_to_free(tmp_path: Path) -> None:
    policy = TenantWorkspacePolicy(tmp_path)

    workspace = policy.load(OWNER_A)

    assert workspace.plan == PlanName.free
    assert not (tmp_path / OWNER_A.tenant_id / "workspace" / "workspace.json").exists()


def test_workspace_and_usage_are_tenant_isolated(tmp_path: Path) -> None:
    policy = TenantWorkspacePolicy(tmp_path)
    policy.save(
        OWNER_A,
        WorkspaceConfig(display_name="Agency A", plan=PlanName.professional),
    )
    policy.save(
        OWNER_B,
        WorkspaceConfig(display_name="Agency B", plan=PlanName.solo),
    )
    policy.record_usage(
        OWNER_A,
        UsageEvent(kind=UsageKind.audit, quantity=2, occurred_at=NOW),
    )

    assert policy.load(OWNER_A).plan == PlanName.professional
    assert policy.load(OWNER_B).plan == PlanName.solo
    assert len(policy.list_usage(OWNER_A)) == 1
    assert policy.list_usage(OWNER_B) == []


def test_viewer_can_read_but_cannot_change_workspace(tmp_path: Path) -> None:
    policy = TenantWorkspacePolicy(tmp_path)
    policy.save(OWNER_A, WorkspaceConfig(display_name="Agency A", plan=PlanName.solo))

    assert policy.load(VIEWER_A).plan == PlanName.solo
    with pytest.raises(IdentityBoundaryError):
        policy.save(
            VIEWER_A,
            WorkspaceConfig(display_name="Forbidden", plan=PlanName.agency),
        )


def test_plan_change_records_actor_and_transition(tmp_path: Path) -> None:
    policy = TenantWorkspacePolicy(tmp_path)

    identifier = policy.record_plan_change(
        OWNER_A,
        previous_plan=PlanName.free,
        new_plan=PlanName.professional,
        changed_at=NOW,
    )
    repeated = policy.record_plan_change(
        OWNER_A,
        previous_plan=PlanName.free,
        new_plan=PlanName.professional,
        changed_at=NOW,
    )

    assert repeated == identifier
    changes = policy.list_plan_changes(VIEWER_A)
    assert len(changes) == 1
    _, event = changes[0]
    assert event.actor_user_id == OWNER_A.user_id
    assert event.previous_plan == PlanName.free
    assert event.new_plan == PlanName.professional
    assert event.changed_at == NOW


def test_viewer_cannot_record_plan_change(tmp_path: Path) -> None:
    policy = TenantWorkspacePolicy(tmp_path)

    with pytest.raises(IdentityBoundaryError):
        policy.record_plan_change(
            VIEWER_A,
            previous_plan=PlanName.free,
            new_plan=PlanName.solo,
            changed_at=NOW,
        )
