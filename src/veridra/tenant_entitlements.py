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
    WorkspacePolicyError,
    WorkspaceStatus,
    WorkspaceStore,
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
    if workspace.status is not WorkspaceStatus.active:
        raise HTTPException(status_code=403, detail="The workspace is suspended.")
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
    workspace = policy.load(identity)
    if workspace.status is not WorkspaceStatus.active:
        raise HTTPException(status_code=403, detail="The workspace is suspended.")
    entitlement = PLAN_CATALOGUE[workspace.plan]
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
) -> str:
    if not tenant_workspace_active(policy, identity):
        return ""
    workspace = policy.load(identity)
    try:
        return policy.usage_ledger(identity).reserve(
            workspace,
            kind,
            quantity=quantity,
        )
    except WorkspacePolicyError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def release_tenant_usage_reservation(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
    reservation_id: str,
) -> None:
    if not reservation_id or not tenant_workspace_active(policy, identity):
        return
    policy.usage_ledger(identity).release_reservation(reservation_id)


def record_tenant_reserved_usage(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
    reservation_id: str,
    kind: UsageKind,
    *,
    quantity: int = 1,
    related_id: str = "",
    note: str = "",
) -> str:
    if not tenant_workspace_active(policy, identity):
        return ""
    return policy.usage_ledger(identity).record_reserved(
        reservation_id,
        UsageEvent(
            kind=kind,
            quantity=quantity,
            occurred_at=datetime.now(UTC),
            related_id=related_id,
            note=note,
        ),
    )


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
    workspace = workspace_store.load()
    if workspace.status is not WorkspaceStatus.active:
        return 0
    return PLAN_CATALOGUE[workspace.plan].max_users


def require_bound_tenant_feature(
    root: Path,
    tenant_id: str,
    feature: str,
) -> None:
    workspace_store, _ = _bound_workspace(root, tenant_id)
    if not workspace_store.path.exists():
        return
    workspace = workspace_store.load()
    if workspace.status is not WorkspaceStatus.active:
        raise HTTPException(status_code=403, detail="The workspace is suspended.")
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
) -> str:
    workspace_store, ledger = _bound_workspace(root, tenant_id)
    if not workspace_store.path.exists():
        return ""
    workspace = workspace_store.load()
    try:
        return ledger.reserve(workspace, kind, quantity=quantity)
    except WorkspacePolicyError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def release_bound_tenant_usage_reservation(
    root: Path,
    tenant_id: str,
    reservation_id: str,
) -> None:
    if not reservation_id:
        return
    _, ledger = _bound_workspace(root, tenant_id)
    ledger.release_reservation(reservation_id)


def record_bound_tenant_reserved_usage(
    root: Path,
    tenant_id: str,
    reservation_id: str,
    kind: UsageKind,
    *,
    quantity: int = 1,
    related_id: str = "",
    note: str = "",
) -> str:
    if not reservation_id:
        return record_bound_tenant_usage(
            root,
            tenant_id,
            kind,
            quantity=quantity,
            related_id=related_id,
            note=note,
        )
    _, ledger = _bound_workspace(root, tenant_id)
    return ledger.record_reserved(
        reservation_id,
        UsageEvent(
            kind=kind,
            quantity=quantity,
            occurred_at=datetime.now(UTC),
            related_id=related_id,
            note=note,
        ),
    )


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
