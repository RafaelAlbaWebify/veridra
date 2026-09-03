from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient

from veridra.agency_change_request_web import router as change_request_router
from veridra.deal_lifecycle import ChangeRequestStatus
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_deal_store import TenantDealStore
from veridra.tenant_prospect_store import TenantProspectStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 9, 3, 11, 0, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="change-request-session",
        authenticated_at=NOW,
    )


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, RequestIdentity, str]:
    identity = _identity()
    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path

    @app.middleware("http")
    async def bind_identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[FastAPIResponse]],
    ) -> FastAPIResponse:
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(change_request_router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    prospect = Prospect(
        business_name="Scope Change Test Dental",
        website="https://example.com",
        locality="Dublin",
        country_code="IE",
    )
    store = TenantProspectStore(tmp_path)
    prospect_id = store.save(identity, prospect)
    return TestClient(app), identity, prospect_id


def _create_change(client: TestClient, prospect_id: str):
    return client.post(
        f"/agency/prospects/{prospect_id}/deal/change-requests",
        headers={"Origin": ORIGIN},
        data={
            "summary": "Add a second booking form to the agreed sprint.",
            "requested_by": "customer",
            "scope_impact": "Adds one form implementation and verification step.",
            "price_impact": "+ EUR 150",
            "timeline_impact": "+ 1 business day",
        },
        follow_redirects=False,
    )


def _update(
    client: TestClient,
    prospect_id: str,
    status: str,
    *,
    decision_reference: str = "",
    resulting_proposal_version: str = "",
):
    return client.post(
        f"/agency/prospects/{prospect_id}/deal/change-requests/1/status",
        headers={"Origin": ORIGIN},
        data={
            "status": status,
            "decision_reference": decision_reference,
            "resulting_proposal_version": resulting_proposal_version,
        },
        follow_redirects=False,
    )


def test_change_request_records_scope_price_and_timeline_impact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity, prospect_id = _client(tmp_path, monkeypatch)

    created = _create_change(client, prospect_id)
    assert created.status_code == 303

    deal = TenantDealStore(tmp_path).load_or_empty(identity, prospect_id)
    assert len(deal.change_requests) == 1
    change = deal.change_requests[0]
    assert change.status is ChangeRequestStatus.requested
    assert change.price_impact == "+ EUR 150"
    assert change.timeline_impact == "+ 1 business day"
    assert deal.next_action == "Review scope, price and timeline impact"

    page = client.get(f"/agency/prospects/{prospect_id}/deal/change-requests")
    assert page.status_code == 200
    assert "Add a second booking form" in page.text
    assert "new proposal version" in page.text


def test_approved_change_requires_decision_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity, prospect_id = _client(tmp_path, monkeypatch)
    assert _create_change(client, prospect_id).status_code == 303

    missing = _update(client, prospect_id, "approved")
    assert missing.status_code == 400

    approved = _update(
        client,
        prospect_id,
        "approved",
        decision_reference="Customer approved +EUR150 scope change by email.",
    )
    assert approved.status_code == 303
    saved = TenantDealStore(tmp_path).load_or_empty(identity, prospect_id)
    assert saved.change_requests[0].status is ChangeRequestStatus.approved
    assert "approved" in saved.change_requests[0].decision_reference.lower()


def test_incorporated_change_requires_resulting_proposal_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity, prospect_id = _client(tmp_path, monkeypatch)
    assert _create_change(client, prospect_id).status_code == 303

    missing_version = _update(client, prospect_id, "incorporated")
    assert missing_version.status_code == 400

    incorporated = _update(
        client,
        prospect_id,
        "incorporated",
        resulting_proposal_version="2",
    )
    assert incorporated.status_code == 303
    saved = TenantDealStore(tmp_path).load_or_empty(identity, prospect_id)
    assert saved.change_requests[0].status is ChangeRequestStatus.incorporated
    assert saved.change_requests[0].resulting_proposal_version == 2
