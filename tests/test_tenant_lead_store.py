from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from veridra.identity_tenancy import IdentityBoundaryError, RequestIdentity, TenantRole
from veridra.lead_store import AuditLead, LeadStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_lead_api import router as tenant_lead_router
from veridra.tenant_lead_store import TenantLeadStore, TenantLeadStoreError

NOW = datetime(2026, 7, 25, 15, 0, tzinfo=UTC)


def _identity(tenant: str, role: TenantRole) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant,
        membership_role=role,
        session_id=f"session-{tenant}-{role.value}",
        authenticated_at=NOW,
    )


def _lead(*, name: str = "Prospect", status: LeadStatus = LeadStatus.new) -> AuditLead:
    return AuditLead(
        form_id="b" * 24,
        website="https://example.com",
        name=name,
        email="prospect@example.com",
        consent_text="I agree to be contacted.",
        consented_at=NOW,
        assessment_id="c" * 24,
        status=status,
    )


def test_tenant_lead_store_isolates_same_identifier_and_roles(tmp_path: Path) -> None:
    store = TenantLeadStore(tmp_path)
    tenant_a_sales = _identity("1" * 24, TenantRole.sales)
    tenant_b_sales = _identity("2" * 24, TenantRole.sales)
    tenant_a_viewer = _identity("1" * 24, TenantRole.viewer)
    tenant_a_analyst = _identity("1" * 24, TenantRole.analyst)

    lead_id_a = store.save(tenant_a_sales, _lead(name="Tenant A"))
    lead_id_b = store.save(tenant_b_sales, _lead(name="Tenant A"))
    assert lead_id_a == lead_id_b
    assert store.load(tenant_a_viewer, store.ref(tenant_a_viewer, lead_id_a)).name == "Tenant A"
    assert store.load(tenant_b_sales, store.ref(tenant_b_sales, lead_id_b)).name == "Tenant A"

    cross_tenant = store.ref(tenant_b_sales, lead_id_b)
    with pytest.raises(IdentityBoundaryError):
        store.load(tenant_a_viewer, cross_tenant)
    with pytest.raises(IdentityBoundaryError):
        store.save(tenant_a_viewer, _lead())
    with pytest.raises(IdentityBoundaryError):
        store.save(tenant_a_analyst, _lead())


def test_tenant_lead_api_crud_uses_bound_identity(tmp_path: Path) -> None:
    identity = _identity("3" * 24, TenantRole.sales)
    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path

    @app.middleware("http")
    async def bind_identity(request: Request, call_next):
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(tenant_lead_router)
    client = TestClient(app)
    payload = _lead().model_dump(mode="json")

    created = client.post("/api/tenant/leads", json=payload)
    assert created.status_code == 201
    lead_id = created.json()["id"]

    listed = client.get("/api/tenant/leads")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [lead_id]

    payload["status"] = "qualified"
    replaced = client.put(f"/api/tenant/leads/{lead_id}", json=payload)
    assert replaced.status_code == 200
    assert replaced.json()["status"] == "qualified"

    fetched = client.get(f"/api/tenant/leads/{lead_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "qualified"

    deleted = client.delete(f"/api/tenant/leads/{lead_id}")
    assert deleted.status_code == 204
    missing = client.get(f"/api/tenant/leads/{lead_id}")
    assert missing.status_code == 404


def test_wrong_tenant_reference_never_falls_back_to_global_store(tmp_path: Path) -> None:
    store = TenantLeadStore(tmp_path)
    sales = _identity("4" * 24, TenantRole.sales)
    lead_id = store.save(sales, _lead())
    wrong_type = store.ref(sales, lead_id).model_copy(update={"object_type": "project"})

    with pytest.raises(TenantLeadStoreError, match="not a lead"):
        store.load(sales, wrong_type)
