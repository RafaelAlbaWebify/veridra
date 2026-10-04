from __future__ import annotations

import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_lead_form_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_form_tenant_binding import (
    LeadFormTenantBindingError,
    SQLiteLeadFormTenantBindingStore,
)
from veridra.lead_store import LeadFormConfig
from veridra.report_profiles import ReportProfile
from veridra.request_security import bind_verified_request_identity
from veridra.runtime_config import RuntimeConfig, RuntimeEnvironment
from veridra.tenant_lead_form_store import TenantLeadFormStore
from veridra.tenant_profile_store import TenantProfileStore
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore

NOW = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="agency-lead-form-owner-0000",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="agency-lead-form-viewer-00",
    authenticated_at=NOW,
)
OTHER_OWNER = RequestIdentity(
    user_id=OWNER.user_id,
    tenant_id="b" * 24,
    membership_role=TenantRole.owner,
    session_id="agency-lead-form-other-0000",
    authenticated_at=NOW,
)


def _client(
    tmp_path: Path,
    *,
    production_plan: PlanName | None = None,
) -> tuple[TestClient, Path, Path, str]:
    root = tmp_path / "tenants"
    database = tmp_path / "identity.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO users (id) VALUES (?)", (OWNER.user_id,))
        connection.execute("INSERT INTO users (id) VALUES (?)", (VIEWER.user_id,))
        connection.execute("INSERT INTO tenants (id) VALUES (?)", (OWNER.tenant_id,))
        connection.execute("INSERT INTO tenants (id) VALUES (?)", (OTHER_OWNER.tenant_id,))
    profile_id = TenantProfileStore(root).save(
        OWNER,
        ReportProfile(organisation_name="Agency Profile"),
    )
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    app.state.veridra_identity_database = database
    if production_plan is not None:
        WorkspaceStore(root / OWNER.tenant_id / "workspace").save(
            WorkspaceConfig(plan=production_plan)
        )
        app.state.veridra_runtime_config = RuntimeConfig(
            environment=RuntimeEnvironment.production,
            identity_database=database,
            tenant_data_root=root,
            trusted_origin="https://app.example.com",
            allowed_hosts=("app.example.com",),
            trusted_proxy_ips=(),
            max_request_body_bytes=1_000_000,
            bind_host="0.0.0.0",
            bind_port=8443,
        )

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "owner":
            bind_verified_request_identity(request, OWNER)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), root, database, profile_id


def _form_data(profile_id: str, *, organisation: str = "Agency One") -> dict[str, str]:
    return {
        "organisation_label": organisation,
        "heading": "Get your website review",
        "introduction": "A bounded public website assessment.",
        "submit_label": "Get report",
        "thank_you_message": "Thanks — we will review this with you.",
        "crawl_profile": "standard",
        "consent_text": "I agree that Agency One may contact me about this audit.",
        "allowed_origins": "https://agency.example",
        "profile_id": profile_id,
        "notification_email": "leads@example.com",
        "cta_url": "https://agency.example/contact",
        "collect_company": "yes",
    }


def _form_model(profile_id: str) -> LeadFormConfig:
    return LeadFormConfig(
        organisation_label="Agency One",
        heading="Get your website review",
        introduction="A bounded public website assessment.",
        submit_label="Get report",
        thank_you_message="Thanks — we will review this with you.",
        crawl_profile="standard",
        consent_text="I agree that Agency One may contact me about this audit.",
        collect_company=True,
        allowed_origins=("https://agency.example",),
        profile_id=profile_id,
        notification_email="leads@example.com",
        cta_url="https://agency.example/contact",
    )


def test_lead_form_page_is_tenant_navigation_and_requires_permission(tmp_path: Path) -> None:
    client, _, _, profile_id = _client(tmp_path)

    owner = client.get("/agency/lead-forms", headers={"x-test-role": "owner"})
    viewer = client.get("/agency/lead-forms", headers={"x-test-role": "viewer"})

    assert owner.status_code == 200
    assert viewer.status_code == 403
    assert "href='/agency/lead-forms' aria-current='page'" in owner.text
    assert "Create lead form" in owner.text
    assert "Quick — up to 10 pages" in owner.text
    assert "Standard — up to 25 pages" in owner.text
    assert "<option value='deep'" not in owner.text
    assert "<option value='custom'" not in owner.text
    assert f"value='{profile_id}'" in owner.text
    assert "href='/lead-forms'" not in owner.text


def test_create_lead_form_saves_tenant_form_and_binding(tmp_path: Path) -> None:
    client, root, database, profile_id = _client(tmp_path)

    response = client.post(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id),
        follow_redirects=False,
    )

    assert response.status_code == 303
    entries = TenantLeadFormStore(root).list(OWNER)
    assert len(entries) == 1
    form_id, form = entries[0]
    assert response.headers["location"] == f"/agency/lead-forms?created={form_id}"
    assert form.organisation_label == "Agency One"
    assert form.thank_you_message == "Thanks — we will review this with you."
    assert form.crawl_profile == "standard"
    assert form.profile_id == profile_id
    assert form.allowed_origins == ("https://agency.example",)
    binding = SQLiteLeadFormTenantBindingStore(database).resolve(form_id)
    assert binding is not None
    assert binding.tenant_id == OWNER.tenant_id


def test_create_binding_conflict_rolls_back_only_new_tenant_form(tmp_path: Path) -> None:
    client, root, database, profile_id = _client(tmp_path)
    form_id = TenantLeadFormStore(root).save(OTHER_OWNER, _form_model(profile_id))
    bindings = SQLiteLeadFormTenantBindingStore(database)
    bindings.bind(
        form_id=form_id,
        tenant_id=OTHER_OWNER.tenant_id,
        created_by_user_id=OTHER_OWNER.user_id,
    )

    response = client.post(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id),
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert TenantLeadFormStore(root).list(OWNER) == []
    assert TenantLeadFormStore(root).load(
        OTHER_OWNER,
        TenantLeadFormStore.ref(OTHER_OWNER, form_id),
    ) == _form_model(profile_id)
    binding = bindings.resolve(form_id)
    assert binding is not None
    assert binding.tenant_id == OTHER_OWNER.tenant_id


def test_edit_lead_form_preserves_id_and_binding(tmp_path: Path) -> None:
    client, root, database, profile_id = _client(tmp_path)
    created = client.post(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id),
        follow_redirects=False,
    )
    form_id = TenantLeadFormStore(root).list(OWNER)[0][0]
    assert created.status_code == 303

    response = client.post(
        f"/agency/lead-forms/{form_id}/edit",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id, organisation="Agency Updated"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    entries = TenantLeadFormStore(root).list(OWNER)
    assert [entry_id for entry_id, _ in entries] == [form_id]
    assert entries[0][1].organisation_label == "Agency Updated"
    binding = SQLiteLeadFormTenantBindingStore(database).resolve(form_id)
    assert binding is not None
    assert binding.tenant_id == OWNER.tenant_id


def test_delete_lead_form_removes_form_and_binding(tmp_path: Path) -> None:
    client, root, database, profile_id = _client(tmp_path)
    client.post(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id),
        follow_redirects=False,
    )
    form_id = TenantLeadFormStore(root).list(OWNER)[0][0]

    response = client.post(
        f"/agency/lead-forms/{form_id}/delete",
        headers={"x-test-role": "owner"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert TenantLeadFormStore(root).list(OWNER) == []
    assert SQLiteLeadFormTenantBindingStore(database).resolve(form_id) is None


def test_delete_unbind_failure_restores_same_form(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, root, database, profile_id = _client(tmp_path)
    client.post(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id),
        follow_redirects=False,
    )
    store = TenantLeadFormStore(root)
    form_id, before = store.list(OWNER)[0]

    def fail_unbind(
        self: SQLiteLeadFormTenantBindingStore,
        *,
        form_id: str,
        tenant_id: str,
    ) -> None:
        raise LeadFormTenantBindingError("simulated unbind failure")

    monkeypatch.setattr(SQLiteLeadFormTenantBindingStore, "unbind", fail_unbind)
    response = client.post(
        f"/agency/lead-forms/{form_id}/delete",
        headers={"x-test-role": "owner"},
        follow_redirects=False,
    )

    assert response.status_code == 409
    entries = store.list(OWNER)
    assert entries == [(form_id, before)]
    binding = SQLiteLeadFormTenantBindingStore(database).resolve(form_id)
    assert binding is not None
    assert binding.tenant_id == OWNER.tenant_id


def test_production_professional_plan_shows_disabled_inventory_but_blocks_creation(
    tmp_path: Path,
) -> None:
    client, root, _, profile_id = _client(
        tmp_path,
        production_plan=PlanName.professional,
    )

    page = client.get("/agency/lead-forms", headers={"x-test-role": "owner"})
    created = client.post(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id),
        follow_redirects=False,
    )

    assert page.status_code == 200
    assert "Embedded lead forms are disabled on the active plan." in page.text
    assert "Create lead form</button>" not in page.text
    assert created.status_code == 403
    assert TenantLeadFormStore(root).list(OWNER) == []


def test_production_agency_plan_can_create_embedded_white_label_form(
    tmp_path: Path,
) -> None:
    client, root, _, profile_id = _client(
        tmp_path,
        production_plan=PlanName.agency,
    )

    response = client.post(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id),
        follow_redirects=False,
    )

    assert response.status_code == 303
    form_id, saved = TenantLeadFormStore(root).list(OWNER)[0]
    assert form_id
    assert saved.profile_id == profile_id


def test_downgraded_workspace_can_delete_existing_lead_form(
    tmp_path: Path,
) -> None:
    client, root, database, profile_id = _client(
        tmp_path,
        production_plan=PlanName.agency,
    )
    created = client.post(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
        data=_form_data(profile_id),
        follow_redirects=False,
    )
    assert created.status_code == 303
    form_id = TenantLeadFormStore(root).list(OWNER)[0][0]

    WorkspaceStore(root / OWNER.tenant_id / "workspace").save(
        WorkspaceConfig(plan=PlanName.professional)
    )

    page = client.get("/agency/lead-forms", headers={"x-test-role": "owner"})
    deleted = client.post(
        f"/agency/lead-forms/{form_id}/delete",
        headers={"x-test-role": "owner"},
        follow_redirects=False,
    )

    assert page.status_code == 200
    assert "Disabled by current plan" in page.text
    assert deleted.status_code == 303
    assert TenantLeadFormStore(root).list(OWNER) == []
    assert SQLiteLeadFormTenantBindingStore(database).resolve(form_id) is None


def test_agency_plan_exposes_embed_setup_with_absolute_production_url(
    tmp_path: Path,
) -> None:
    client, root, database, _ = _client(
        tmp_path,
        production_plan=PlanName.agency,
    )
    identity = OWNER
    form_id = TenantLeadFormStore(root).save(
        identity,
        LeadFormConfig(
            organisation_label="Setup Agency",
            consent_text="I agree to be contacted.",
            allowed_origins=("https://agency.example",),
        ),
    )
    SQLiteLeadFormTenantBindingStore(database).bind(
        form_id=form_id,
        tenant_id=identity.tenant_id,
        created_by_user_id=identity.user_id,
        created_at=NOW,
    )

    index = client.get(
        "/agency/lead-forms",
        headers={"x-test-role": "owner"},
    )
    setup = client.get(
        f"/agency/lead-forms/{form_id}/setup",
        headers={"x-test-role": "owner"},
    )

    assert index.status_code == 200
    assert f"/agency/lead-forms/{form_id}/setup" in index.text
    assert setup.status_code == 200
    assert "Embed setup" in setup.text
    assert f"https://app.example.com/embed/audit/{form_id}" in setup.text
    assert "https://agency.example" in setup.text
    assert "&lt;iframe src=&quot;https://app.example.com/embed/audit/" in setup.text
    assert "Inbound leads" in setup.text


def test_non_entitled_plan_cannot_open_embed_setup(
    tmp_path: Path,
) -> None:
    client, root, database, _ = _client(
        tmp_path,
        production_plan=PlanName.professional,
    )
    identity = OWNER
    form_id = TenantLeadFormStore(root).save(
        identity,
        LeadFormConfig(
            organisation_label="Preserved form",
            consent_text="I agree to be contacted.",
        ),
    )
    SQLiteLeadFormTenantBindingStore(tmp_path / "identity.sqlite3").bind(
        form_id=form_id,
        tenant_id=identity.tenant_id,
        created_by_user_id=identity.user_id,
        created_at=NOW,
    )

    response = client.get(
        f"/agency/lead-forms/{form_id}/setup",
        headers={"x-test-role": "owner"},
    )

    assert response.status_code == 403
