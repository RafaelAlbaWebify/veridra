from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.tenant_entitlements import (
    bound_tenant_max_users,
    release_tenant_usage_reservation,
    require_tenant_feature,
    require_tenant_project_capacity,
    reserve_tenant_usage,
)
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import (
    PLAN_CATALOGUE,
    PlanName,
    UsageKind,
    WorkspaceConfig,
    WorkspaceStatus,
    WorkspaceStore,
)

NOW = datetime(2026, 10, 2, 9, 40, tzinfo=UTC)
TENANT = "a" * 24
OTHER_TENANT = "b" * 24
USER = "1" * 24


def _identity(tenant_id: str) -> RequestIdentity:
    return RequestIdentity(
        user_id=USER,
        tenant_id=tenant_id,
        membership_role=TenantRole.owner,
        session_id=("c" if tenant_id == TENANT else "d") * 24,
        authenticated_at=NOW,
    )


def _save_workspace(
    root: Path,
    identity: RequestIdentity,
    *,
    plan: PlanName,
    status: WorkspaceStatus = WorkspaceStatus.active,
) -> None:
    WorkspaceStore(root / identity.tenant_id / "workspace").save(
        WorkspaceConfig(plan=plan, status=status)
    )


def test_hosted_commercial_integrity_survives_plan_and_status_transitions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tenants"
    identity = _identity(TENANT)
    other = _identity(OTHER_TENANT)
    policy = TenantWorkspacePolicy(root)
    projects = TenantProjectStore(root)

    # Agency: full commercial feature set is available and tenant storage is isolated.
    _save_workspace(root, identity, plan=PlanName.agency)
    _save_workspace(root, other, plan=PlanName.agency)
    require_tenant_feature(policy, identity, "white_label")
    require_tenant_feature(policy, identity, "embedded_lead_forms")

    owner_project = projects.save_with_capacity(
        identity,
        ClientProject.build(
            name="Agency client",
            target_url="https://example.com",
        ),
        max_projects=PLAN_CATALOGUE[PlanName.agency].max_projects,
    )
    projects.save_with_capacity(
        other,
        ClientProject.build(
            name="Other tenant client",
            target_url="https://other.example",
        ),
        max_projects=PLAN_CATALOGUE[PlanName.agency].max_projects,
    )
    assert [entry.id for entry in projects.list(identity)] == [owner_project]
    assert [entry.name for entry in projects.list(other)] == ["Other tenant client"]

    # Professional: white label remains available but embedded lead forms stop.
    _save_workspace(root, identity, plan=PlanName.professional)
    require_tenant_feature(policy, identity, "white_label")
    with pytest.raises(HTTPException) as embedded_block:
        require_tenant_feature(policy, identity, "embedded_lead_forms")
    assert embedded_block.value.status_code == 403

    # Free: existing project remains readable, but new project/PDF/monitoring capacity stops.
    _save_workspace(root, identity, plan=PlanName.free)
    assert projects.load(identity, projects.ref(identity, owner_project)).name == "Agency client"
    with pytest.raises(HTTPException) as project_block:
        require_tenant_project_capacity(
            policy,
            identity,
            current_projects=len(projects.list(identity)),
        )
    assert project_block.value.status_code == 429
    with pytest.raises(HTTPException) as pdf_block:
        reserve_tenant_usage(policy, identity, UsageKind.pdf)
    assert pdf_block.value.status_code == 429
    assert PLAN_CATALOGUE[PlanName.free].monthly_monitoring_runs == 0

    # Suspended: commercial mutation/features and seats are disabled without deleting data.
    _save_workspace(
        root,
        identity,
        plan=PlanName.agency,
        status=WorkspaceStatus.suspended,
    )
    with pytest.raises(HTTPException) as suspended_feature:
        require_tenant_feature(policy, identity, "white_label")
    assert suspended_feature.value.status_code == 403
    with pytest.raises(HTTPException) as suspended_project:
        require_tenant_project_capacity(
            policy,
            identity,
            current_projects=len(projects.list(identity)),
        )
    assert suspended_project.value.status_code == 403
    with pytest.raises(HTTPException):
        reserve_tenant_usage(policy, identity, UsageKind.pdf)
    assert bound_tenant_max_users(root, identity.tenant_id) == 0
    assert projects.load(identity, projects.ref(identity, owner_project)).name == "Agency client"

    # Recovery: restoring an active Agency workspace re-enables paid capability without leaks.
    _save_workspace(root, identity, plan=PlanName.agency)
    require_tenant_feature(policy, identity, "white_label")
    require_tenant_feature(policy, identity, "embedded_lead_forms")
    reservation_id = reserve_tenant_usage(policy, identity, UsageKind.pdf)
    assert reservation_id
    release_tenant_usage_reservation(policy, identity, reservation_id)
    reservation_dir = root / identity.tenant_id / "workspace" / "usage-reservations"
    assert list(reservation_dir.glob("*.json")) == []
