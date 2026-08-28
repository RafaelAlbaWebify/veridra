from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient

from veridra.agency_prospect_web import router as agency_prospect_router
from veridra.customer_store import CustomerSourceType
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect, ProspectStatus
from veridra.prospect_activity import ProspectActivityType, TenantProspectActivityStore
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_customer_store import TenantCustomerStore
from veridra.tenant_prospect_store import TenantProspectStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


def _identity(*, tenant: str = "b") -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant * 24,
        membership_role=TenantRole.sales,
        session_id="prospect-activity-session-001",
        authenticated_at=NOW,
    )


def _prospect() -> Prospect:
    return Prospect(
        business_name="No Site Dental",
        sector="Dental clinic",
        locality="Dublin",
        country_code="IE",
        phone="+35310000000",
        contact_email="hello@nositedental.example",
        status=ProspectStatus.approved_for_outreach,
        human_verified=True,
    )


def test_legacy_prospect_without_follow_up_fields_loads_with_safe_defaults() -> None:
    legacy = Prospect.model_validate(
        {
            "business_name": "Legacy Dental",
            "sector": "Dental clinic",
            "locality": "Dublin",
            "country_code": "IE",
            "status": "contacted",
        }
    )

    assert legacy.last_contacted_at is None
    assert legacy.next_follow_up_at is None
    assert legacy.next_action == ""


def test_activity_log_is_append_only_and_records_meaningful_changes(tmp_path: Path) -> None:
    identity = _identity()
    store = TenantProspectStore(tmp_path)
    prospect = _prospect()
    prospect_id = store.save(identity, prospect)
    activity = TenantProspectActivityStore(tmp_path)
    path = tmp_path / identity.tenant_id / "prospect-activity" / f"{prospect_id}.jsonl"

    original_bytes = path.read_bytes()
    original_events = activity.list(identity, prospect_id)
    assert [event.event_type for event in original_events] == [ProspectActivityType.created]

    contacted = prospect.model_copy(
        update={
            "status": ProspectStatus.contacted,
            "last_contacted_at": datetime(2026, 8, 28, 9, 30, tzinfo=UTC),
            "next_follow_up_at": datetime(2026, 8, 31, 10, 0, tzinfo=UTC),
            "next_action": "Call the clinic manager",
            "outreach_offer": "Website Improvement Sprint",
            "message_variant": "dublin-dental-v1",
            "commercial_note": "Personalised email sent.",
        }
    )
    store.replace(identity, store.ref(identity, prospect_id), contacted)

    updated_bytes = path.read_bytes()
    events = activity.list(identity, prospect_id)
    event_types = [event.event_type for event in events]

    assert updated_bytes.startswith(original_bytes)
    assert event_types == [
        ProspectActivityType.created,
        ProspectActivityType.stage_changed,
        ProspectActivityType.contact_recorded,
        ProspectActivityType.follow_up_changed,
        ProspectActivityType.commercial_changed,
        ProspectActivityType.note_changed,
    ]
    assert events[1].metadata == {"from": "approved_for_outreach", "to": "contacted"}


def test_follow_up_fields_persist_tenant_scoped(tmp_path: Path) -> None:
    identity = _identity()
    other_identity = _identity(tenant="c")
    store = TenantProspectStore(tmp_path)
    prospect_id = store.save(identity, _prospect())
    saved = store.load(identity, store.ref(identity, prospect_id))
    updated = saved.model_copy(
        update={
            "last_contacted_at": datetime(2026, 8, 28, 9, 30, tzinfo=UTC),
            "next_follow_up_at": datetime(2026, 8, 31, 10, 0, tzinfo=UTC),
            "next_action": "Follow up by phone",
        }
    )
    store.replace(identity, store.ref(identity, prospect_id), updated)

    reloaded = store.load(identity, store.ref(identity, prospect_id))
    assert reloaded.last_contacted_at == datetime(2026, 8, 28, 9, 30, tzinfo=UTC)
    assert reloaded.next_follow_up_at == datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
    assert reloaded.next_action == "Follow up by phone"
    assert store.list(other_identity) == []


def test_sales_user_can_convert_prospect_to_customer_and_history_is_preserved(
    tmp_path: Path,
) -> None:
    identity = _identity()
    store = TenantProspectStore(tmp_path)
    prospect = _prospect()
    prospect_id = store.save(identity, prospect)
    before = TenantProspectActivityStore(tmp_path).list(identity, prospect_id)

    customer_prospect = prospect.model_copy(
        update={
            "status": ProspectStatus.customer,
            "outreach_offer": "Website Improvement Sprint",
            "commercial_note": "Client accepted the sprint.",
        }
    )
    store.replace(identity, store.ref(identity, prospect_id), customer_prospect)

    customers = TenantCustomerStore(tmp_path).list(identity)
    events = TenantProspectActivityStore(tmp_path).list(identity, prospect_id)

    assert len(customers) == 1
    _, customer = customers[0]
    assert customer.source_type is CustomerSourceType.prospect
    assert customer.source_id == prospect_id
    assert customer.business_name == "No Site Dental"
    assert customer.website is None
    assert events[: len(before)] == before
    assert ProspectActivityType.customer_converted in [event.event_type for event in events]


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


def test_prospect_ui_saves_follow_up_and_renders_activity_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    store = TenantProspectStore(tmp_path)
    prospect_id = store.save(identity, _prospect())

    response = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={
            "status": "contacted",
            "outreach_offer": "Website Improvement Sprint",
            "message_variant": "dublin-dental-v1",
            "commercial_loss_reason": "",
            "commercial_note": "Email sent to clinic.",
            "last_contacted_at": "2026-08-28T09:30",
            "next_follow_up_at": "2026-08-31T10:00",
            "next_action": "Call the clinic manager",
        },
        follow_redirects=False,
    )
    detail = client.get(f"/agency/prospects/{prospect_id}")
    index = client.get("/agency/prospects")
    saved = store.load(identity, store.ref(identity, prospect_id))

    assert response.status_code == 303
    assert saved.status is ProspectStatus.contacted
    assert saved.next_action == "Call the clinic manager"
    assert saved.last_contacted_at is not None
    assert saved.next_follow_up_at is not None
    assert detail.status_code == 200
    assert "Activity history" in detail.text
    assert "Stage Changed" in detail.text
    assert "Follow Up Changed" in detail.text
    assert "Call the clinic manager" in detail.text
    assert index.status_code == 200
    assert "Follow-up" in index.text
    assert "Call the clinic manager" in index.text
