from __future__ import annotations

from types import SimpleNamespace

import pytest

from veridra.tenant_entitlements import tenant_workspace_active


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
