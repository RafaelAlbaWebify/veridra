from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.identity_tenancy import IdentityBoundaryError, RequestIdentity, TenantRole
from veridra.prospect import (
    Prospect,
    ProspectDecision,
    ProspectRejectionReason,
    ProspectStatus,
    StageAQualification,
)
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_prospect_api import router as tenant_prospect_router
from veridra.tenant_prospect_store import TenantProspectStore

NOW = datetime(2026, 8, 22, 17, 30, tzinfo=UTC)


def _identity(tenant: str, role: TenantRole) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant,
        membership_role=role,
        session_id=f"session-{tenant}-{role.value}",
        authenticated_at=NOW,
    )


def _qualification(*, score_two: bool = True) -> StageAQualification:
    value = 2 if score_two else 1
    return StageAQualification(
        active_real_business=value,
        website_commercial_importance=value,
        business_economic_value=value,
        business_size_fit=value,
        decision_maker_reachability=value,
        website_manageability=value,
        no_existing_web_team=value,
        reason="Active owner-managed business with a commercially important website.",
    )


def _prospect(*, name: str = "Murphy Roofing Ltd") -> Prospect:
    return Prospect(
        business_name=name,
        website="https://example.ie",
        sector="Roofing",
        locality="Cork",
        administrative_area="Cork",
        country_code="IE",
        phone="+353000000000",
        contact_email="owner@example.ie",
        provider="leadmap-local",
        provider_key="fixture-business-01",
        evidence_summary="Business observed in local territory research.",
        qualification=_qualification(),
        status=ProspectStatus.shortlisted,
        created_at=NOW,
        updated_at=NOW,
    )


def test_stage_a_qualification_preserves_leads_commercial_gate() -> None:
    strong = _qualification()
    secondary = _qualification(score_two=False)
    rejected = secondary.model_copy(
        update={"rejection_reason": ProspectRejectionReason.agency_present}
    )

    assert strong.score == 14
    assert strong.decision is ProspectDecision.send_to_audit
    assert secondary.score == 7
    assert secondary.decision is ProspectDecision.reject
    assert rejected.decision is ProspectDecision.reject


def test_stage_a_hold_range_is_explicit() -> None:
    qualification = StageAQualification(
        active_real_business=2,
        website_commercial_importance=2,
        business_economic_value=1,
        business_size_fit=1,
        decision_maker_reachability=1,
        website_manageability=1,
        no_existing_web_team=1,
        reason="Plausible SMB but more evidence is needed before an audit.",
    )

    assert qualification.score == 9
    assert qualification.decision is ProspectDecision.hold


def test_unsuitable_prospect_requires_rejection_reason() -> None:
    with pytest.raises(ValueError, match="rejection reason"):
        _prospect().model_copy(
            update={"status": ProspectStatus.unsuitable, "rejection_reason": None}
        ).model_validate(
            {
                **_prospect().model_dump(mode="json"),
                "status": "unsuitable",
                "rejection_reason": None,
            }
        )


def test_tenant_prospect_store_isolates_research_records(tmp_path: Path) -> None:
    store = TenantProspectStore(tmp_path)
    tenant_a_sales = _identity("1" * 24, TenantRole.sales)
    tenant_b_sales = _identity("2" * 24, TenantRole.sales)
    tenant_a_viewer = _identity("1" * 24, TenantRole.viewer)

    prospect_id_a = store.save(tenant_a_sales, _prospect())
    prospect_id_b = store.save(tenant_b_sales, _prospect())

    assert prospect_id_a == prospect_id_b
    assert store.load(
        tenant_a_viewer,
        store.ref(tenant_a_viewer, prospect_id_a),
    ).business_name == "Murphy Roofing Ltd"

    with pytest.raises(IdentityBoundaryError):
        store.load(
            tenant_a_viewer,
            store.ref(tenant_b_sales, prospect_id_b),
        )


def test_tenant_prospect_api_crud_uses_bound_identity(tmp_path: Path) -> None:
    identity = _identity("3" * 24, TenantRole.sales)
    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path

    @app.middleware("http")
    async def bind_identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(tenant_prospect_router)
    client = TestClient(app)
    payload = _prospect().model_dump(mode="json")

    created = client.post("/api/tenant/prospects", json=payload)
    assert created.status_code == 201
    prospect_id = created.json()["id"]

    listed = client.get("/api/tenant/prospects")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [prospect_id]

    payload["status"] = "ready_for_audit"
    replaced = client.put(f"/api/tenant/prospects/{prospect_id}", json=payload)
    assert replaced.status_code == 200
    assert replaced.json()["status"] == "ready_for_audit"

    fetched = client.get(f"/api/tenant/prospects/{prospect_id}")
    assert fetched.status_code == 200
    assert fetched.json()["qualification"]["reason"].startswith("Active")

    deleted = client.delete(f"/api/tenant/prospects/{prospect_id}")
    assert deleted.status_code == 204
