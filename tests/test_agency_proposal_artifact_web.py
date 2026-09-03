from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient

from veridra.agency_proposal_artifact_web import router as proposal_artifact_router
from veridra.deal_lifecycle import DealRecord, ProposalStatus, ProposalVersion
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_deal_store import TenantDealStore
from veridra.tenant_prospect_store import TenantProspectStore

NOW = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="proposal-artifact-session",
        authenticated_at=NOW,
    )


def _client(tmp_path: Path) -> tuple[TestClient, RequestIdentity, str]:
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

    app.include_router(proposal_artifact_router)
    prospect = Prospect.model_validate(
        {
            "business_name": "International Dental Test",
            "website": "https://example.com",
            "locality": "Dublin",
            "country_code": "IE",
        }
    )
    prospect_store = TenantProspectStore(tmp_path)
    prospect_id = prospect_store.save(identity, prospect)
    proposal = ProposalVersion(
        version=1,
        status=ProposalStatus.accepted,
        title="Website Improvement Sprint",
        scope="Fix agreed mobile booking and trust issues.",
        deliverables="Bounded fixes, verification and final report.",
        exclusions="Booking platform replacement.",
        assumptions="Existing hosting remains in place.",
        timeline="5 business days after access",
        price_amount=650.0,
        currency="EUR",
        recurring_amount=99.0,
        recurring_cadence="monthly",
        valid_until=date(2026, 9, 17),
        acceptance_reference="Accepted externally by email on 2026-09-03.",
    )
    TenantDealStore(tmp_path).save(
        identity,
        DealRecord(prospect_id=prospect_id, proposals=(proposal,)),
    )
    return TestClient(app), identity, prospect_id


def test_proposal_preview_is_customer_readable_and_boundary_explicit(tmp_path: Path) -> None:
    client, _, prospect_id = _client(tmp_path)
    response = client.get(
        f"/agency/prospects/{prospect_id}/deal/proposals/1/artifact"
    )

    assert response.status_code == 200
    assert "Website Improvement Sprint" in response.text
    assert "International Dental Test" in response.text
    assert "EUR 650.00" in response.text
    assert "EUR 99.00 monthly" in response.text
    assert "Accepted externally by email" in response.text
    assert "not an accounting invoice" in response.text
    assert "payment receipt" in response.text


def test_proposal_download_has_safe_attachment_filename(tmp_path: Path) -> None:
    client, _, prospect_id = _client(tmp_path)
    response = client.get(
        f"/agency/prospects/{prospect_id}/deal/proposals/1/download"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "International-Dental-Test-proposal-v1.html" in disposition
