from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_activity import LeadActivityType, TenantLeadActivityStore
from veridra.lead_store import AuditLead, LeadStatus
from veridra.tenant_lead_store import TenantLeadStore


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.owner,
        session_id="c" * 24,
        authenticated_at=datetime.now(UTC),
    )


def _lead() -> AuditLead:
    return AuditLead(
        form_id="d" * 24,
        website="https://example.com",
        name="Example Owner",
        email="owner@example.com",
        company="Example Ltd",
        consent_text="I agree",
        consented_at=datetime.now(UTC),
        assessment_id="e" * 24,
    )


def test_legacy_lead_json_loads_with_commercial_defaults() -> None:
    raw = _lead().model_dump(mode="json")
    for key in (
        "offer_service",
        "quoted_value",
        "expected_value",
        "currency",
        "won_at",
        "lost_at",
        "loss_reason",
    ):
        raw.pop(key, None)

    loaded = AuditLead.model_validate_json(json.dumps(raw))

    assert loaded.offer_service == ""
    assert loaded.quoted_value is None
    assert loaded.expected_value is None
    assert loaded.currency == "EUR"
    assert loaded.won_at is None
    assert loaded.lost_at is None
    assert loaded.loss_reason == ""


def test_lead_accepts_webify_offer_and_values() -> None:
    lead = _lead().model_copy(
        update={
            "offer_service": "Website Improvement Sprint",
            "quoted_value": Decimal("650.00"),
            "expected_value": Decimal("500.00"),
            "currency": "EUR",
        }
    )

    validated = AuditLead.model_validate(lead.model_dump(mode="python"))

    assert validated.offer_service == "Website Improvement Sprint"
    assert validated.quoted_value == Decimal("650.00")
    assert validated.expected_value == Decimal("500.00")


def test_tenant_store_appends_activity_without_rewriting_old_events(tmp_path: Path) -> None:
    identity = _identity()
    store = TenantLeadStore(tmp_path)
    lead = _lead()
    lead_id = store.save(identity, lead)

    updated = lead.model_copy(
        update={
            "status": LeadStatus.contacted,
            "next_action": "Call Monday",
            "offer_service": "Website Improvement Sprint",
            "quoted_value": Decimal("650.00"),
        }
    )
    store.replace(identity, store.ref(identity, lead_id), updated)

    events = TenantLeadActivityStore(tmp_path).list(identity, lead_id)
    event_types = [event.event_type for event in events]

    assert event_types[0] is LeadActivityType.created
    assert LeadActivityType.stage_changed in event_types
    assert LeadActivityType.follow_up_changed in event_types
    assert LeadActivityType.commercial_changed in event_types

    before = list(events)
    store.replace(identity, store.ref(identity, lead_id), updated.model_copy(update={"notes": "Called"}))
    after = TenantLeadActivityStore(tmp_path).list(identity, lead_id)

    assert after[: len(before)] == before
    assert after[-1].event_type is LeadActivityType.note_changed
