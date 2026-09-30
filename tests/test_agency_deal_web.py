from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient

from veridra.agency_deal_web import router as agency_deal_router
from veridra.agency_proposal_transition_web import router as proposal_transition_router
from veridra.agency_prospect_web import router as agency_prospect_router
from veridra.agency_reply_transition_web import router as reply_transition_router
from veridra.customer_store import CustomerSourceType, customer_identifier
from veridra.deal_lifecycle import ProposalStatus, RecurringQualification, ReplyOutcome
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import ProspectStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_customer_store import TenantCustomerStore
from veridra.tenant_deal_store import TenantDealStore
from veridra.tenant_prospect_store import TenantProspectStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="d" * 24,
        authenticated_at=NOW,
    )


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RequestIdentity]:
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

    app.include_router(reply_transition_router)
    app.include_router(proposal_transition_router)
    app.include_router(agency_deal_router)
    app.include_router(agency_prospect_router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    return TestClient(app), identity


def _create_prospect(client: TestClient) -> str:
    response = client.post(
        "/agency/prospects/new",
        headers={"Origin": ORIGIN},
        data={
            "business_name": "Lifecycle Test Dental",
            "website": "https://example.com",
            "sector": "Dental clinic",
            "locality": "Dublin",
            "administrative_area": "Dublin",
            "country_code": "IE",
            "contact_email": "owner@example.com",
            "evidence_summary": "Synthetic sales lifecycle acceptance fixture.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return cast(str, response.headers["location"].rsplit("/", 1)[-1])


def _approve_outreach(
    tmp_path: Path,
    identity: RequestIdentity,
    prospect_id: str,
) -> None:
    store = TenantProspectStore(tmp_path)
    prospect = store.load(identity, store.ref(identity, prospect_id))
    store.replace(
        identity,
        store.ref(identity, prospect_id),
        prospect.model_copy(
            update={
                "status": ProspectStatus.contacted,
                "outreach_eligible": True,
            }
        ),
    )


def test_positive_reply_discovery_and_accepted_proposal_are_persistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _create_prospect(client)
    _approve_outreach(tmp_path, identity, prospect_id)

    reply = client.post(
        f"/agency/prospects/{prospect_id}/deal/reply",
        headers={"Origin": ORIGIN},
        data={
            "reply_outcome": "positive",
            "conversation_summary": "Owner asked for a clear scope and price.",
            "next_action": "Run a 20-minute discovery call",
        },
        follow_redirects=False,
    )
    assert reply.status_code == 303

    discovery = client.post(
        f"/agency/prospects/{prospect_id}/deal/discovery",
        headers={"Origin": ORIGIN},
        data={
            "goals": "Reduce mobile booking friction and improve trust.",
            "current_platform": "WordPress",
            "hosting": "External managed host",
            "decision_maker": "Clinic owner",
            "urgency": "This month",
            "constraints": "No booking-platform replacement.",
            "access_readiness": "Admin access can be provided after booking.",
            "measurable_scope": "Fix agreed mobile and trust issues on current site.",
            "deliverables": "Audit, bounded fixes, verification, final report.",
            "exclusions": "Copywriting and booking-system replacement.",
            "assumptions": "Existing hosting remains in place.",
            "timeline": "5 business days after access",
        },
        follow_redirects=False,
    )
    assert discovery.status_code == 303

    blocked_recurring = client.post(
        f"/agency/prospects/{prospect_id}/deal/proposals",
        headers={"Origin": ORIGIN},
        data={
            "title": "Unqualified recurring offer",
            "scope": "Fix agreed mobile and trust issues on current site.",
            "deliverables": "Audit, bounded fixes, verification, final report.",
            "timeline": "5 business days after access",
            "price_amount": "650.00",
            "currency": "EUR",
            "recurring_amount": "99.00",
            "recurring_cadence": "monthly",
            "valid_until": "2026-10-15",
        },
        follow_redirects=False,
    )
    assert blocked_recurring.status_code == 409

    qualification = client.post(
        f"/agency/prospects/{prospect_id}/deal/recurring-qualification",
        headers={"Origin": ORIGIN},
        data={
            "recurring_qualification": "presence_care",
            "recurring_qualification_evidence": (
                "Recurring monitoring is justified by ongoing change and maintenance needs."
            ),
        },
        follow_redirects=False,
    )
    assert qualification.status_code == 303

    proposal = client.post(
        f"/agency/prospects/{prospect_id}/deal/proposals",
        headers={"Origin": ORIGIN},
        data={
            "title": "Website Improvement Sprint",
            "scope": "Fix agreed mobile and trust issues on current site.",
            "deliverables": "Audit, bounded fixes, verification, final report.",
            "exclusions": "Copywriting and booking-system replacement.",
            "assumptions": "Existing hosting remains in place.",
            "timeline": "5 business days after access",
            "price_amount": "650.00",
            "currency": "EUR",
            "recurring_amount": "99.00",
            "recurring_cadence": "monthly",
            "valid_until": "2026-10-15",
        },
        follow_redirects=False,
    )
    assert proposal.status_code == 303

    sent = client.post(
        f"/agency/prospects/{prospect_id}/deal/proposals/1/status",
        headers={"Origin": ORIGIN},
        data={"status": "sent", "acceptance_reference": ""},
        follow_redirects=False,
    )
    assert sent.status_code == 303

    missing_evidence = client.post(
        f"/agency/prospects/{prospect_id}/deal/proposals/1/status",
        headers={"Origin": ORIGIN},
        data={"status": "accepted", "acceptance_reference": ""},
        follow_redirects=False,
    )
    assert missing_evidence.status_code == 400

    accepted = client.post(
        f"/agency/prospects/{prospect_id}/deal/proposals/1/status",
        headers={"Origin": ORIGIN},
        data={
            "status": "accepted",
            "acceptance_reference": "Customer accepted proposal v1 by email on 2026-09-03",
        },
        follow_redirects=False,
    )
    assert accepted.status_code == 303

    deal = TenantDealStore(tmp_path).load_or_empty(identity, prospect_id)
    prospect_saved = TenantProspectStore(tmp_path).load(
        identity,
        TenantProspectStore.ref(identity, prospect_id),
    )
    assert deal.reply_outcome is ReplyOutcome.positive
    assert deal.recurring_qualification is RecurringQualification.presence_care
    assert deal.recurring_qualification_evidence
    assert deal.discovery is not None
    assert deal.discovery.current_platform == "WordPress"
    assert len(deal.proposals) == 1
    assert deal.proposals[0].status is ProposalStatus.accepted
    assert deal.has_accepted_proposal is True
    assert prospect_saved.status.value == "customer"
    assert "agreement and payment" in prospect_saved.next_action.lower()
    customer_id = customer_identifier(CustomerSourceType.prospect, prospect_id)
    customer = TenantCustomerStore(tmp_path).load(
        identity,
        TenantCustomerStore.ref(identity, customer_id),
    )
    assert customer.offer_service == "Website Improvement Sprint"
    assert customer.quoted_value == Decimal("650.00")
    assert customer.currency == "EUR"
    assert customer.billing.invoice_amount == Decimal("650.00")
    assert customer.billing.status.value == "reference_pending"
    assert customer.booking_gate_required is True
    assert customer.work_may_start is False

    page = client.get(f"/agency/prospects/{prospect_id}/deal")
    assert page.status_code == 200
    assert "Sales / proposal" in page.text
    assert "Proposal accepted" in page.text
    assert "agreement and payment evidence before work starts" in page.text


def test_proposal_requires_discovery_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    prospect_id = _create_prospect(client)

    response = client.post(
        f"/agency/prospects/{prospect_id}/deal/proposals",
        headers={"Origin": ORIGIN},
        data={
            "title": "Premature quote",
            "scope": "Unknown",
            "deliverables": "Unknown",
            "timeline": "Unknown",
            "price_amount": "650",
            "currency": "EUR",
            "valid_until": "2026-10-15",
        },
        follow_redirects=False,
    )

    assert response.status_code == 409


def test_proposal_form_uses_canonical_offer_without_inventing_price(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _create_prospect(client)
    _approve_outreach(tmp_path, identity, prospect_id)
    reply = client.post(
        f"/agency/prospects/{prospect_id}/deal/reply",
        headers={"Origin": ORIGIN},
        data={
            "reply_outcome": "positive",
            "conversation_summary": "Owner requested a scoped proposal.",
            "next_action": "Complete discovery",
        },
        follow_redirects=False,
    )
    assert reply.status_code == 303
    discovery = client.post(
        f"/agency/prospects/{prospect_id}/deal/discovery",
        headers={"Origin": ORIGIN},
        data={
            "goals": "Establish a bounded baseline.",
            "measurable_scope": "Assess the agreed public website.",
            "deliverables": "Baseline, prioritised findings and final report.",
            "timeline": "5 business days after access",
        },
        follow_redirects=False,
    )
    assert discovery.status_code == 303

    standalone = client.get(f"/agency/prospects/{prospect_id}/deal")
    assert standalone.status_code == 200
    assert "Webify Digital Presence Assessment &amp; Improvement" in standalone.text
    assert "Pricing is intentionally operator-confirmed" in standalone.text
    assert "name='price_amount'" in standalone.text
    price_with_default = (
        "name='price_amount' type='number' step='0.01' min='0.01' required value="
    )
    assert price_with_default not in standalone.text

    qualification = client.post(
        f"/agency/prospects/{prospect_id}/deal/recurring-qualification",
        headers={"Origin": ORIGIN},
        data={
            "recurring_qualification": "presence_care",
            "recurring_qualification_evidence": (
                "Ongoing changes justify monitoring and bounded care."
            ),
        },
        follow_redirects=False,
    )
    assert qualification.status_code == 303
    recurring = client.get(f"/agency/prospects/{prospect_id}/deal")
    assert recurring.status_code == 200
    assert "value='Webify Presence Care'" in recurring.text
    assert "Presence Care qualified." in recurring.text
