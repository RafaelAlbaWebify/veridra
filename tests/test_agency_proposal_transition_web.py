from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient

from veridra.agency_proposal_transition_web import router as transition_router
from veridra.deal_lifecycle import DealRecord, ProposalStatus, ProposalVersion
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_deal_store import TenantDealStore
from veridra.tenant_prospect_store import TenantProspectStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 9, 3, 10, 30, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="proposal-transition-session",
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

    app.include_router(transition_router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    prospect = Prospect(
        business_name="Transition Test Dental",
        website="https://example.com",
        locality="Dublin",
        country_code="IE",
    )
    prospect_store = TenantProspectStore(tmp_path)
    prospect_id = prospect_store.save(identity, prospect)
    proposal = ProposalVersion(
        version=1,
        title="Website Improvement Sprint",
        scope="Bounded website fixes.",
        deliverables="Fixes and verification report.",
        timeline="5 business days",
        price_amount=650.0,
        currency="EUR",
        valid_until=date(2026, 9, 30),
    )
    TenantDealStore(tmp_path).save(
        identity,
        DealRecord(prospect_id=prospect_id, proposals=(proposal,)),
    )
    return TestClient(app), identity, prospect_id


def _status(
    client: TestClient,
    prospect_id: str,
    status: str,
    acceptance_reference: str = "",
):
    return client.post(
        f"/agency/prospects/{prospect_id}/deal/proposals/1/status",
        headers={"Origin": ORIGIN},
        data={
            "status": status,
            "acceptance_reference": acceptance_reference,
        },
        follow_redirects=False,
    )


def test_proposal_requires_sent_before_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity, prospect_id = _client(tmp_path, monkeypatch)

    premature = _status(
        client,
        prospect_id,
        "accepted",
        "Accepted externally by email.",
    )
    assert premature.status_code == 409

    sent = _status(client, prospect_id, "sent")
    assert sent.status_code == 303
    accepted = _status(
        client,
        prospect_id,
        "accepted",
        "Accepted externally by email.",
    )
    assert accepted.status_code == 303

    saved = TenantDealStore(tmp_path).load_or_empty(identity, prospect_id)
    assert saved.proposals[0].status is ProposalStatus.accepted
    assert saved.proposals[0].acceptance_reference == "Accepted externally by email."


def test_terminal_proposal_cannot_be_rewritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity, prospect_id = _client(tmp_path, monkeypatch)
    assert _status(client, prospect_id, "sent").status_code == 303
    assert _status(client, prospect_id, "declined").status_code == 303

    reopened = _status(client, prospect_id, "sent")
    assert reopened.status_code == 409
    saved = TenantDealStore(tmp_path).load_or_empty(identity, prospect_id)
    assert saved.proposals[0].status is ProposalStatus.declined


def test_sent_proposal_can_expire_but_not_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity, prospect_id = _client(tmp_path, monkeypatch)
    assert _status(client, prospect_id, "sent").status_code == 303
    assert _status(client, prospect_id, "expired").status_code == 303
    assert _status(client, prospect_id, "sent").status_code == 409

    saved = TenantDealStore(tmp_path).load_or_empty(identity, prospect_id)
    assert saved.proposals[0].status is ProposalStatus.expired
