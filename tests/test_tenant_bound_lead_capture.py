from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.requests import Request

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.lead_form_tenant_binding import SQLiteLeadFormTenantBindingStore
from veridra.lead_store import AuditLead, LeadFormConfig, LeadFormStore, LeadStore
from veridra.runtime import app as runtime_app
from veridra.tenant_bound_lead_capture import _save_lead

NOW = datetime(2026, 7, 25, 17, 0, tzinfo=UTC)


def _request(app: FastAPI) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/embed/audit/test",
            "headers": [],
            "app": app,
        }
    )


def _lead(form_id: str, *, name: str) -> AuditLead:
    return AuditLead(
        form_id=form_id,
        website="https://example.com",
        name=name,
        email="prospect@example.com",
        consent_text="I agree to be contacted.",
        consented_at=NOW,
        assessment_id="c" * 24,
    )


def test_runtime_registers_one_public_submission_route() -> None:
    matching = [
        route
        for route in runtime_app.routes
        if isinstance(route, APIRoute)
        and route.path == "/embed/audit/{form_id}"
        and route.methods == {"POST"}
    ]
    assert len(matching) == 1
    assert matching[0].endpoint.__name__ == "submit_tenant_bound_embedded_audit"


def test_bound_capture_writes_only_to_tenant_store(tmp_path: Path, monkeypatch) -> None:
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
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_tenant_data_root = data_root / "tenants"

    lead_id = _save_lead(_request(app), _lead(form_id, name="Bound prospect"))

    assert (
        data_root / "tenants" / first.tenant_id / "leads" / f"{lead_id}.json"
    ).exists()
    assert LeadStore().list_leads() == []


def test_unbound_capture_preserves_legacy_store(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(data_root))
    database = tmp_path / "identity.sqlite3"
    SQLiteIdentityBootstrap(database).create_first_owner(
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
            organisation_label="Legacy form",
            consent_text="I agree to be contacted.",
        )
    )
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_tenant_data_root = data_root / "tenants"

    lead_id = _save_lead(_request(app), _lead(form_id, name="Legacy prospect"))

    assert (data_root / "leads" / "records" / f"{lead_id}.json").exists()
    assert not (data_root / "tenants").exists()
