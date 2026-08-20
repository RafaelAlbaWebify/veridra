from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_form_tenant_binding import SQLiteLeadFormTenantBindingStore
from veridra.lead_store import LeadFormConfig
from veridra.tenant_bound_lead_capture import router
from veridra.tenant_lead_form_store import TenantLeadFormStore
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import PlanName, WorkspaceConfig

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _bound_form(tmp_path: Path) -> tuple[TestClient, TenantWorkspacePolicy, RequestIdentity, str]:
    root = tmp_path / "tenants"
    database = tmp_path / "identity.sqlite3"
    first = SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password="owner-correct-horse-battery",
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    identity = RequestIdentity(
        user_id=first.user_id,
        tenant_id=first.tenant_id,
        membership_role=TenantRole.owner,
        session_id="b" * 24,
        authenticated_at=NOW,
    )
    form_id = TenantLeadFormStore(root).save(
        identity,
        LeadFormConfig(
            organisation_label="Customer one",
            consent_text="I agree to be contacted.",
        ),
    )
    SQLiteLeadFormTenantBindingStore(database).bind(
        form_id=form_id,
        tenant_id=identity.tenant_id,
        created_by_user_id=identity.user_id,
        created_at=NOW,
    )
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_tenant_data_root = root
    app.include_router(router)
    return TestClient(app), TenantWorkspacePolicy(root), identity, form_id


def test_bound_form_stops_serving_after_downgrade_and_recovers_on_agency(
    tmp_path: Path,
) -> None:
    client, policy, identity, form_id = _bound_form(tmp_path)

    policy.save(identity, WorkspaceConfig(plan=PlanName.professional))
    downgraded = client.get(f"/embed/audit/{form_id}")

    policy.save(identity, WorkspaceConfig(plan=PlanName.agency))
    entitled = client.get(f"/embed/audit/{form_id}")

    assert downgraded.status_code == 403
    assert downgraded.json()["detail"] == (
        "The active professional plan does not include embedded lead forms."
    )
    assert entitled.status_code == 200
    assert "Customer one" in entitled.text
