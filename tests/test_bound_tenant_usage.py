from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from veridra.assessment_project_conversion_api import (
    AssessmentProjectConversion,
    convert_assessment,
)
from veridra.core import demo_assessment
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.tenant_entitlements import (
    record_bound_tenant_usage,
    reserve_bound_tenant_usage,
)
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import PlanName, UsageKind, WorkspaceConfig, usage_period

NOW = datetime(2026, 7, 27, 18, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="bound-tenant-usage-owner",
    authenticated_at=NOW,
)
OTHER_TENANT_ID = "b" * 24


def _request(root: Path) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/tenant/projects/from-assessment",
            "headers": [],
            "app": app,
        }
    )


def test_bound_free_plan_rejects_lead_submission(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    TenantWorkspacePolicy(root).save(OWNER, WorkspaceConfig(plan=PlanName.free))

    with pytest.raises(HTTPException) as exc_info:
        reserve_bound_tenant_usage(
            root,
            OWNER.tenant_id,
            UsageKind.lead_submission,
        )

    assert exc_info.value.status_code == 429


def test_bound_usage_is_recorded_only_for_derived_tenant(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    policy = TenantWorkspacePolicy(root)
    policy.save(OWNER, WorkspaceConfig(plan=PlanName.agency))

    record_bound_tenant_usage(
        root,
        OWNER.tenant_id,
        UsageKind.audit,
        related_id="assessment-one",
        note="bound audit",
    )

    workspace = policy.load(OWNER)
    totals = policy.usage_ledger(OWNER).totals(usage_period(workspace))
    assert totals[UsageKind.audit] == 1
    assert not (root / OTHER_TENANT_ID / "workspace" / "usage").exists()


def test_direct_conversion_uses_tenant_project_capacity(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    policy = TenantWorkspacePolicy(root)
    policy.save(OWNER, WorkspaceConfig(plan=PlanName.free))
    projects = TenantProjectStore(root)
    projects.save(
        OWNER,
        ClientProject.build(name="Existing", target_url="https://example.com"),
    )
    payload = AssessmentProjectConversion(
        assessment=demo_assessment().model_copy(
            update={"target": "https://example.net/"}
        ),
        project_name="Second",
    )

    with pytest.raises(HTTPException) as exc_info:
        convert_assessment(payload, _request(root), OWNER)

    assert exc_info.value.status_code == 429
    assert len(projects.list(OWNER)) == 1
