from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient
from httpx import Response

from veridra.agency_reply_transition_web import router as reply_router
from veridra.deal_lifecycle import ReplyOutcome
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect, ProspectStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_deal_store import TenantDealStore
from veridra.tenant_prospect_store import TenantProspectStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 9, 3, 11, 30, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="reply-transition-session",
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

    app.include_router(reply_router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    store = TenantProspectStore(tmp_path)
    prospect = Prospect.model_validate(
        {
            "business_name": "Reply Test Dental",
            "website": "https://example.com",
            "locality": "Dublin",
            "country_code": "IE",
        }
    )
    prospect_id = store.save(identity, prospect)
    return TestClient(app), identity, prospect_id


def _reply(client: TestClient, prospect_id: str, outcome: str) -> Response:
    return client.post(
        f"/agency/prospects/{prospect_id}/deal/reply",
        headers={"Origin": ORIGIN},
        data={
            "reply_outcome": outcome,
            "conversation_summary": "Synthetic reply evidence.",
            "next_action": "",
        },
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    ("outcome", "expected_fragment", "expected_status"),
    [
        ("positive", "complete discovery", ProspectStatus.responded),
        ("negative", "loss reason", ProspectStatus.responded),
        ("price_request", "before quoting", ProspectStatus.responded),
        ("call_request", "discovery call", ProspectStatus.conversation),
        ("different_scope", "assess fit", ProspectStatus.conversation),
        ("no_response", "follow-up date", ProspectStatus.responded),
    ],
)
def test_reply_outcomes_drive_specific_operator_next_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    expected_fragment: str,
    expected_status: ProspectStatus,
) -> None:
    client, identity, prospect_id = _client(tmp_path, monkeypatch)

    response = _reply(client, prospect_id, outcome)
    assert response.status_code == 303

    deal = TenantDealStore(tmp_path).load_or_empty(identity, prospect_id)
    prospect = TenantProspectStore(tmp_path).load(
        identity,
        TenantProspectStore.ref(identity, prospect_id),
    )
    assert deal.reply_outcome is ReplyOutcome(outcome)
    assert expected_fragment in deal.next_action.lower()
    assert prospect.status is expected_status
    assert prospect.next_action == deal.next_action


def test_reply_requires_observed_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, prospect_id = _client(tmp_path, monkeypatch)
    response = _reply(client, prospect_id, "")
    assert response.status_code == 400
