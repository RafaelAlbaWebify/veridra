from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_form_tenant_binding import SQLiteLeadFormTenantBindingStore
from veridra.lead_form_tenant_binding_api import router as binding_router
from veridra.lead_store import AuditLead, LeadFormConfig, LeadFormStore, LeadStore
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_lead_store import TenantLeadStore

NOW = datetime(2026, 7, 25, 16, 0, tzinfo=UTC)


def _lead(form_id: str) -> AuditLead:
    return AuditLead(
        form_id=form_id,
        website=HttpUrl("https://example.com"),
        name="Public prospect",
        email="prospect@example.com",
        consent_text="I agree to be contacted.",
        consented_at=NOW,
        assessment_id="c" * 24,
    )


def _app(database: Path, identity: RequestIdentity) -> FastAPI:
    app = FastAPI()
    app.state.veridra_identity_database = database

    @app.middleware("http")
    async def bind_identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(binding_router)
    return app


def test_binding_is_tenant_scoped_and_public_capture_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(data_root))
    database = tmp_path / "identity.sqlite3"
    bootstrapped = SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password="owner-correct-horse-battery",
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    identity = RequestIdentity(
        user_id=bootstrapped.user_id,
        tenant_id=bootstrapped.tenant_id,
        membership_role=TenantRole.owner,
        session_id="binding-session",
        authenticated_at=NOW,
    )
    form_id = LeadFormStore().save(
        LeadFormConfig(
            organisation_label="Customer one",
            consent_text="I agree to be contacted.",
        )
    )
    client = TestClient(_app(database, identity))

    bound = client.put(f"/api/tenant/lead-forms/{form_id}/binding")
    assert bound.status_code == 200
    assert bound.json() == {"form_id": form_id, "tenant_id": identity.tenant_id}
    assert client.put(f"/api/tenant/lead-forms/{form_id}/binding").status_code == 409

    binding = SQLiteLeadFormTenantBindingStore(database).resolve(form_id)
    assert binding is not None
    lead_id = TenantLeadStore(data_root / "tenants").save_bound_public_capture(
        tenant_id=binding.tenant_id,
        lead=_lead(form_id),
    )
    tenant_path = data_root / "tenants" / identity.tenant_id / "leads" / f"{lead_id}.json"
    assert tenant_path.exists()
    assert LeadStore().list_leads() == []

    fetched = client.get(f"/api/tenant/lead-forms/{form_id}/binding")
    assert fetched.status_code == 200
    assert client.delete(f"/api/tenant/lead-forms/{form_id}/binding").status_code == 204
    assert SQLiteLeadFormTenantBindingStore(database).resolve(form_id) is None


def test_binding_is_hidden_from_another_tenant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(data_root))
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
    form_id = LeadFormStore().save(
        LeadFormConfig(
            organisation_label="Customer one",
            consent_text="I agree to be contacted.",
        )
    )
    SQLiteLeadFormTenantBindingStore(database).bind(
        form_id=form_id,
        tenant_id=first.tenant_id,
        created_by_user_id=first.user_id,
        created_at=NOW,
    )
    other_identity = RequestIdentity(
        user_id="d" * 24,
        tenant_id="e" * 24,
        membership_role=TenantRole.owner,
        session_id="other-session",
        authenticated_at=NOW,
    )
    client = TestClient(_app(database, other_identity))

    assert client.get(f"/api/tenant/lead-forms/{form_id}/binding").status_code == 404
    assert client.delete(f"/api/tenant/lead-forms/{form_id}/binding").status_code == 404
    assert SQLiteLeadFormTenantBindingStore(database).resolve(form_id) is not None
