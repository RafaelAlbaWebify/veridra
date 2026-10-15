from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from veridra.tenant_entitlements import (
    bound_tenant_max_users,
    record_bound_tenant_usage,
    require_bound_tenant_feature,
    reserve_bound_tenant_usage,
    tenant_workspace_active,
)
from veridra.workspace_policy import UsageKind


@pytest.mark.parametrize(
    ("environment", "local_agency"),
    [("operator", ""), ("production", "1")],
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
    assert tenant_workspace_active(policy, SimpleNamespace()) is False


@pytest.mark.parametrize(
    ("environment", "local_agency"),
    [("operator", ""), ("production", "1")],
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
