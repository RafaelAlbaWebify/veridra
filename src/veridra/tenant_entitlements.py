from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from .identity_tenancy import RequestIdentity
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import (
    PLAN_CATALOGUE,
    UsageEvent,
    UsageKind,
    UsageLedger,
    WorkspaceConfig,
    WorkspaceStore,
    quota_decision,
)


def tenant_workspace_active(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
) -> bool:
    return policy.workspace_store(identity).path.exists()


def active_workspace(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
) -> WorkspaceConfig:
    return policy.load(identity)


def _feature_allowed(workspace: WorkspaceConfig, feature: str) -> bool:
    entitlement = PLAN_CATALOGUE[workspace.plan]
    allowed = {
        "white_label": entitlement.white_label,
        "embedded_lead_forms": entitlement.embedded_lead_forms,
    }.get(feature)
    if allowed is None:
        raise ValueError("Unknown workspace entitlement feature.")
    return allowed


def require_tenant_feature(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
    feature: str,
) -> None:
    if not tenant_workspace_active(policy, identity):
        return
    workspace = policy.load(identity)
    if not _feature_allowed(workspace, feature):
        raise HTTPException(
            status_code=403,
            detail=(
                f"The active {workspace.plan.value} plan does not include "
                f"{feature.replace('_', ' ')}."
            ),
        )


def require_tenant_project_capacity(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
    current_projects: int,
) -> None:
    if not tenant_workspace_active(policy, identity):
        return
    entitlement = PLAN_CATALOGUE[policy.load(identity).plan]
    if current_projects >= entitlement.max_projects:
        raise HTTPException(
            status_code=429,
            detail=(
                f"The active {entitlement.name.value} plan project allowance is "
                "exhausted."
            ),
        )


def reserve_tenant_usage(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
    kind: UsageKind,
    *,
    quantity: int = 1,
) -> None:
    if not tenant_workspace_active(policy, identity):
        return
    workspace = policy.load(identity)
    decision = quota_decision(
        workspace,
        policy.usage_ledger(identity),
        kind,
        requested=quantity,
    )
    if not decision.allowed:
        raise HTTPException(status_code=429, detail=decision.reason)


def record_tenant_usage(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
    kind: UsageKind,
    *,
    quantity: int = 1,
    related_id: str = "",
    note: str = "",
) -> str:
    if not tenant_workspace_active(policy, identity):
        return ""
    return policy.record_usage(
        identity,
        UsageEvent(
            kind=kind,
            quantity=quantity,
            occurred_at=datetime.now(UTC),
            related_id=related_id,
            note=note,
        ),
    )


def _bound_workspace(
    root: Path,
    tenant_id: str,
) -> tuple[WorkspaceStore, UsageLedger]:
    directory = root / tenant_id / "workspace"
    return WorkspaceStore(directory), UsageLedger(directory)


def bound_tenant_max_users(root: Path, tenant_id: str) -> int | None:
    workspace_store, _ = _bound_workspace(root, tenant_id)
    if not workspace_store.path.exists():
        return None
    return PLAN_CATALOGUE[workspace_store.load().plan].max_users


def require_bound_tenant_feature(
    root: Path,
    tenant_id: str,
    feature: str,
) -> None:
    workspace_store, _ = _bound_workspace(root, tenant_id)
    if not workspace_store.path.exists():
        return
    workspace = workspace_store.load()
    if not _feature_allowed(workspace, feature):
        raise HTTPException(
            status_code=403,
            detail=(
                f"The active {workspace.plan.value} plan does not include "
                f"{feature.replace('_', ' ')}."
            ),
        )


def reserve_bound_tenant_usage(
    root: Path,
    tenant_id: str,
    kind: UsageKind,
    *,
    quantity: int = 1,
) -> None:
    workspace_store, ledger = _bound_workspace(root, tenant_id)
    if not workspace_store.path.exists():
        return
    workspace = workspace_store.load()
    decision = quota_decision(workspace, ledger, kind, requested=quantity)
    if not decision.allowed:
        raise HTTPException(status_code=429, detail=decision.reason)


def record_bound_tenant_usage(
    root: Path,
    tenant_id: str,
    kind: UsageKind,
    *,
    quantity: int = 1,
    related_id: str = "",
    note: str = "",
) -> str:
    workspace_store, ledger = _bound_workspace(root, tenant_id)
    if not workspace_store.path.exists():
        return ""
    return ledger.record(
        UsageEvent(
            kind=kind,
            quantity=quantity,
            occurred_at=datetime.now(UTC),
            related_id=related_id,
            note=note,
        )
    )
