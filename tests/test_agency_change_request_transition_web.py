from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient
from httpx import Response

from veridra.agency_change_request_transition_web import router as transition_router
from veridra.deal_lifecycle import (
    ChangeRequestStatus,
    DealRecord,
    ProposalVersion,
    ScopeChangeRequest,
)
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_deal_store import TenantDealStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
PROSPECT_ID = "c" * 24


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="change-transition-session",
        authenticated_at=NOW,
    )


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, RequestIdentity]:
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
    proposal = ProposalVersion(
        version=2,
        title="Revised scope",
        scope="Original scope plus approved booking form.",
        deliverables="Website fixes and verification.",
        timeline="6 business days",
        price_amount=800,
        currency="EUR",
        valid_until=date(2026, 9, 30),
    )
    change = ScopeChangeRequest(
        sequence=1,
        summary="Add booking form",
        scope_impact="Adds implementation and verification.",
    )
    TenantDealStore(tmp_path).save(
        identity,
        DealRecord(
            prospect_id=PROSPECT_ID,
            proposals=(proposal,),
            change_requests=(change,),
        ),
    )
    return TestClient(app), identity


def _update(
    client: TestClient,
    status: str,
    *,
    decision_reference: str = "",
    resulting_proposal_version: str = "",
) -> Response:
    return cast(
        Response,
        client.post(
            f"/agency/prospects/{PROSPECT_ID}/deal/change-requests/1/status",
            headers={"Origin": ORIGIN},
            data={
                "status": status,
                "decision_reference": decision_reference,
                "resulting_proposal_version": resulting_proposal_version,
            },
            follow_redirects=False,
        ),
    )


def test_change_must_be_approved_before_incorporation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)

    premature = _update(client, "incorporated", resulting_proposal_version="2")
    assert premature.status_code == 409

    approved = _update(
        client,
        "approved",
        decision_reference="Customer approved change by email.",
    )
    assert approved.status_code == 303

    incorporated = _update(client, "incorporated", resulting_proposal_version="2")
    assert incorporated.status_code == 303
    saved = TenantDealStore(tmp_path).load_or_empty(identity, PROSPECT_ID)
    assert saved.change_requests[0].status is ChangeRequestStatus.incorporated
    assert saved.change_requests[0].resulting_proposal_version == 2
    assert saved.change_requests[0].decision_reference == "Customer approved change by email."


def test_incorporation_rejects_unknown_proposal_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    assert (
        _update(
            client,
            "approved",
            decision_reference="Customer approved change by email.",
        ).status_code
        == 303
    )

    unknown = _update(client, "incorporated", resulting_proposal_version="99")
    assert unknown.status_code == 409


def test_declined_change_is_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    declined = _update(
        client,
        "declined",
        decision_reference="Customer declined the additional price.",
    )
    assert declined.status_code == 303
    assert _update(client, "reviewing").status_code == 409
    saved = TenantDealStore(tmp_path).load_or_empty(identity, PROSPECT_ID)
    assert saved.change_requests[0].status is ChangeRequestStatus.declined
