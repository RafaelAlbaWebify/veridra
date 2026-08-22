from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient
from httpx import Response

from veridra.agency_prospect_web import router as agency_prospect_router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import ProspectStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_prospect_store import TenantProspectStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 8, 22, 18, 30, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="prospect-workbench-session",
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

    app.include_router(agency_prospect_router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    return TestClient(app), identity


def _create(client: TestClient) -> Response:
    return cast(
        Response,
        client.post(
            "/agency/prospects/new",
            headers={"Origin": ORIGIN},
            data={
                "business_name": "Vigo Dental Clinic",
                "website": "https://example.es",
                "sector": "Dental clinic",
                "locality": "Vigo",
                "administrative_area": "Pontevedra",
                "country_code": "ES",
                "phone": "+34986000000",
                "contact_email": "hello@example.es",
                "evidence_summary": "Active local clinic with an older public website.",
            },
            follow_redirects=False,
        ),
    )


def test_operator_can_create_review_and_start_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    created = _create(client)
    assert created.status_code == 303
    detail_url = created.headers["location"]

    index = client.get("/agency/prospects")
    detail = client.get(detail_url)

    assert index.status_code == 200
    assert "Webify prospects" in index.text
    assert "Vigo Dental Clinic" in index.text
    assert "Inbound leads" in index.text
    assert detail.status_code == 200
    assert "Stage A · Commercial fit" in detail.text
    assert "/agency/quick-audit?target=https%3A%2F%2Fexample.es%2F" in detail.text


def test_duplicate_manual_creation_does_not_overwrite_existing_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    first = _create(client)
    prospect_id = first.headers["location"].rsplit("/", 1)[-1]
    store = TenantProspectStore(tmp_path)
    original = store.load(identity, store.ref(identity, prospect_id))
    qualified = original.model_copy(
        update={"status": ProspectStatus.contacted, "human_verified": True}
    )
    store.replace(identity, store.ref(identity, prospect_id), qualified)

    duplicate = _create(client)
    saved = store.load(identity, store.ref(identity, prospect_id))

    assert duplicate.status_code == 200
    assert "Prospect already exists" in duplicate.text
    assert saved.status is ProspectStatus.contacted
    assert saved.human_verified is True


def test_strong_stage_a_score_moves_prospect_to_ready_for_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    created = _create(client)
    prospect_id = created.headers["location"].rsplit("/", 1)[-1]

    response = client.post(
        f"/agency/prospects/{prospect_id}/qualify",
        headers={"Origin": ORIGIN},
        data={
            "active_real_business": "2",
            "website_commercial_importance": "2",
            "business_economic_value": "2",
            "business_size_fit": "2",
            "decision_maker_reachability": "1",
            "website_manageability": "2",
            "no_existing_web_team": "2",
            "reason": (
                "Active clinic, reachable owner and a commercially important manageable site."
            ),
            "rejection_reason": "",
        },
        follow_redirects=False,
    )

    saved = TenantProspectStore(tmp_path).load(
        identity,
        TenantProspectStore.ref(identity, prospect_id),
    )
    assert response.status_code == 303
    assert saved.status is ProspectStatus.ready_for_audit
    assert saved.qualification is not None
    assert saved.qualification.score == 13
    assert saved.human_verified is True


def test_explicit_rejection_records_reason_and_marks_unsuitable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    created = _create(client)
    prospect_id = created.headers["location"].rsplit("/", 1)[-1]

    response = client.post(
        f"/agency/prospects/{prospect_id}/qualify",
        headers={"Origin": ORIGIN},
        data={
            "active_real_business": "2",
            "website_commercial_importance": "1",
            "business_economic_value": "1",
            "business_size_fit": "1",
            "decision_maker_reachability": "0",
            "website_manageability": "1",
            "no_existing_web_team": "0",
            "reason": "The business appears active but there is no realistic direct contact route.",
            "rejection_reason": "NO_CONTACT_ROUTE",
        },
        follow_redirects=False,
    )

    store = TenantProspectStore(tmp_path)
    saved = store.load(identity, store.ref(identity, prospect_id))
    assert response.status_code == 303
    assert saved.status is ProspectStatus.unsuitable
    assert saved.rejection_reason is not None
    assert saved.rejection_reason.value == "NO_CONTACT_ROUTE"


def test_prospect_mutations_reject_missing_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    response = client.post(
        "/agency/prospects/new",
        data={"business_name": "No Origin Ltd", "country_code": "ES"},
        follow_redirects=False,
    )

    assert response.status_code == 403
