from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import HttpUrl
from starlette.requests import Request
from starlette.routing import BaseRoute

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_form_tenant_binding import SQLiteLeadFormTenantBindingStore
from veridra.lead_store import AuditLead, LeadFormConfig, LeadFormStore, LeadStore
from veridra.lead_web import router as legacy_lead_router
from veridra.runtime import app as runtime_app
from veridra.tenant_bound_lead_capture import _resolve_form, _save_lead
from veridra.tenant_bound_lead_capture import router as tenant_capture_router
from veridra.tenant_lead_form_store import TenantLeadFormStore

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


def _identity(user_id: str, tenant_id: str) -> RequestIdentity:
    return RequestIdentity(
        user_id=user_id,
        tenant_id=tenant_id,
        membership_role=TenantRole.owner,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _lead(form_id: str, *, name: str) -> AuditLead:
    return AuditLead(
        form_id=form_id,
        website=HttpUrl("https://example.com"),
        name=name,
        email="prospect@example.com",
        consent_text="I agree to be contacted.",
        consented_at=NOW,
        assessment_id="c" * 24,
    )


def _public_routes(routes: Sequence[BaseRoute], method: str) -> list[APIRoute]:
    return [
        route
        for route in routes
        if isinstance(route, APIRoute)
        and route.path == "/embed/audit/{form_id}"
        and route.methods == {method}
    ]


def test_runtime_composes_only_the_replacement_public_routes() -> None:
    assert _public_routes(legacy_lead_router.routes, "GET") == []
    assert _public_routes(legacy_lead_router.routes, "POST") == []
    replacement_get = _public_routes(tenant_capture_router.routes, "GET")
    replacement_post = _public_routes(tenant_capture_router.routes, "POST")
    assert len(replacement_get) == 1
    assert len(replacement_post) == 1
    assert replacement_get[0].endpoint.__name__ == "tenant_bound_embedded_audit_form"
    assert replacement_post[0].endpoint.__name__ == "submit_tenant_bound_embedded_audit"
    assert runtime_app is not None


def test_bound_tenant_form_loads_without_legacy_copy(
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
    identity = _identity(first.user_id, first.tenant_id)
    form_id = TenantLeadFormStore(data_root / "tenants").save(
        identity,
        LeadFormConfig(
            organisation_label="Tenant form",
            consent_text="I agree to be contacted.",
        ),
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

    resolved = _resolve_form(_request(app), form_id)

    assert resolved.organisation_label == "Tenant form"
    assert LeadFormStore().list() == []


def test_bound_legacy_form_remains_compatible(
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
            organisation_label="Legacy bound form",
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

    resolved = _resolve_form(_request(app), form_id)

    assert resolved.organisation_label == "Legacy bound form"


def test_bound_capture_writes_only_to_tenant_store(
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
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_tenant_data_root = data_root / "tenants"

    lead_id = _save_lead(_request(app), _lead(form_id, name="Bound prospect"))

    assert (
        data_root / "tenants" / first.tenant_id / "leads" / f"{lead_id}.json"
    ).exists()
    assert LeadStore().list_leads() == []


def test_unbound_capture_preserves_legacy_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
