from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import (
    PlanName,
    UsageEvent,
    UsageKind,
    WorkspaceConfig,
    WorkspaceStore,
)

NOW = datetime(2026, 7, 27, 21, 0, tzinfo=UTC)
IDENTITY = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="workspace-migration-boundary",
    authenticated_at=NOW,
)

LEGACY_NAMES = {
    "workspace_policy_active",
    "active_entitlements",
    "require_feature",
    "require_project_capacity",
    "reserve_usage",
    "record_usage",
}


def test_tenant_policy_ignores_ambiguous_global_workspace_and_usage(tmp_path: Path) -> None:
    global_store = WorkspaceStore(tmp_path / "workspace")
    global_store.save(WorkspaceConfig(plan=PlanName.agency))
    global_store.directory.joinpath("usage").mkdir(parents=True, exist_ok=True)
    global_store.directory.joinpath("usage", "legacy.json").write_text(
        UsageEvent(
            kind=UsageKind.audit,
            quantity=99,
            occurred_at=NOW,
            related_id="ambiguous-global-event",
        ).model_dump_json(),
        encoding="utf-8",
    )

    policy = TenantWorkspacePolicy(tmp_path / "tenants")

    assert policy.load(IDENTITY).plan == PlanName.free
    assert policy.list_usage(IDENTITY) == []
    assert not (tmp_path / "tenants" / IDENTITY.tenant_id).exists()


def test_supported_source_does_not_import_legacy_global_helpers() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "veridra"
    offenders: list[str] = []
    for path in sorted(source_root.glob("*.py")):
        if path.name == "workspace_web.py":
            continue
        content = path.read_text(encoding="utf-8")
        if "workspace_web import" not in content:
            continue
        if any(name in content for name in LEGACY_NAMES):
            offenders.append(path.name)

    assert offenders == []
