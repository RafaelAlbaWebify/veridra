from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from veridra.identity_tenancy import RequestIdentity
from veridra.runtime_config import private_webify_runtime_enabled
from veridra.tenant_entitlements import (
    bound_tenant_max_users,
    record_bound_tenant_usage,
    require_bound_tenant_feature,
    reserve_bound_tenant_usage,
    tenant_workspace_active,
)
from veridra.tenant_workspace_policy import (
    TenantWorkspacePolicy,
    TenantWorkspacePolicyError,
)
from veridra.workspace_policy import (
    PlanName,
    UsageKind,
    UsageLedger,
    WorkspaceConfig,
    WorkspaceStatus,
    quota_decision,
)


@pytest.mark.parametrize(
    ("environment", "local_agency"),
    [("local", "")],
)
def test_webify_private_runtime_ignores_historical_workspace_plan_files(
    monkeypatch: pytest.MonkeyPatch, environment: str, local_agency: str
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", environment)
    if local_agency:
        monkeypatch.setenv("VERIDRA_LOCAL_AGENCY", local_agency)
    else:
        monkeypatch.delenv("VERIDRA_LOCAL_AGENCY", raising=False)

    # A real legacy WorkspaceStore would contain historical SaaS subscription
    # state, but private Webify operation must never even consult it.
    policy = SimpleNamespace(
        workspace_store=lambda identity: (_ for _ in ()).throw(
            AssertionError("Legacy SaaS workspace policy must not be loaded")
        )
    )
    assert tenant_workspace_active(
        cast(TenantWorkspacePolicy, policy), cast(RequestIdentity, SimpleNamespace())
    ) is False


@pytest.mark.parametrize(
    ("environment", "local_agency"),
    [("local", "")],
)
def test_webify_private_runtime_bypasses_bound_saas_limits_without_workspace_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: str,
    local_agency: str,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", environment)
    if local_agency:
        monkeypatch.setenv("VERIDRA_LOCAL_AGENCY", local_agency)
    else:
        monkeypatch.delenv("VERIDRA_LOCAL_AGENCY", raising=False)

    # A corrupt or suspended legacy subscription must not block Webify.
    # No tenant workspace directory is created as a side effect.
    root = tmp_path / "clients"
    tenant_id = "a" * 24
    assert bound_tenant_max_users(root, tenant_id) is None
    require_bound_tenant_feature(root, tenant_id, "white_label")
    assert reserve_bound_tenant_usage(root, tenant_id, UsageKind.audit) == ""
    assert record_bound_tenant_usage(root, tenant_id, UsageKind.audit) == ""
    assert not root.exists()


@pytest.mark.parametrize(
    ("environment", "local_agency", "expected"),
    [
        ("operator", "", False),
        ("local", "", True),
        ("production", "1", False),
        ("test", "", False),
    ],
)
def test_legacy_quota_boundary_is_explicit(
    environment: str, local_agency: str, expected: bool
) -> None:
    assert private_webify_runtime_enabled(
        {"VERIDRA_ENV": environment, "VERIDRA_LOCAL_AGENCY": local_agency}
    ) is expected


@pytest.mark.parametrize(
    ("environment", "local_agency"),
    [("local", "")],
)
def test_webify_private_runtime_refuses_new_saas_plan_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: str,
    local_agency: str,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", environment)
    if local_agency:
        monkeypatch.setenv("VERIDRA_LOCAL_AGENCY", local_agency)
    else:
        monkeypatch.delenv("VERIDRA_LOCAL_AGENCY", raising=False)
    policy = TenantWorkspacePolicy(tmp_path / "tenants")
    with pytest.raises(TenantWorkspacePolicyError, match="plan changes are retired"):
        policy.record_plan_change(
            cast(RequestIdentity, SimpleNamespace()),
            previous_plan=PlanName.free,
            new_plan=PlanName.agency,
        )
    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    ("environment", "local_agency"),
    [("local", "")],
)
def test_private_webify_quota_engine_does_not_read_historical_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: str,
    local_agency: str,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", environment)
    if local_agency:
        monkeypatch.setenv("VERIDRA_LOCAL_AGENCY", local_agency)
    else:
        monkeypatch.delenv("VERIDRA_LOCAL_AGENCY", raising=False)
    ledger = UsageLedger(tmp_path / "historical-workspace")
    monkeypatch.setattr(
        ledger,
        "effective_totals",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("SaaS quota ledger must not be consulted")
        ),
    )
    decision = quota_decision(
        WorkspaceConfig(plan=PlanName.free, status=WorkspaceStatus.suspended),
        ledger,
        UsageKind.pdf,
    )
    assert decision.allowed
    assert decision.limit is None
    assert decision.remaining is None
    assert not (tmp_path / "historical-workspace").exists()


@pytest.mark.parametrize(
    ("environment", "local_agency"),
    [("local", "")],
)
def test_private_webify_direct_reservation_does_not_create_legacy_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    local_agency: str,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", environment)
    if local_agency:
        monkeypatch.setenv("VERIDRA_LOCAL_AGENCY", local_agency)
    else:
        monkeypatch.delenv("VERIDRA_LOCAL_AGENCY", raising=False)

    root = tmp_path / "historical-workspace"
    ledger = UsageLedger(root)
    reservation = ledger.reserve(
        WorkspaceConfig(plan=PlanName.free, status=WorkspaceStatus.suspended),
        UsageKind.pdf,
    )
    assert reservation == ""
    assert not root.exists()
