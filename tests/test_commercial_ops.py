from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl, TypeAdapter

from veridra.commercial_ops import (
    EngagementKind,
    EngagementLink,
    EngagementStore,
    RetentionPolicy,
    apply_retention,
    commercial_summary,
    engagement_token,
    retention_preview,
)
from veridra.email_delivery import EmailAttemptStore
from veridra.lead_delivery import LeadDeliveryStore
from veridra.lead_store import AuditLead, LeadFormConfig, LeadFormStore, LeadStatus, LeadStore
from veridra.runtime import app

_FORM_ID = "a" * 24
_ASSESSMENT_ID = "b" * 24


def _lead(*, consented_at: datetime, status: LeadStatus = LeadStatus.new) -> AuditLead:
    return AuditLead(
        form_id=_FORM_ID,
        website=TypeAdapter(HttpUrl).validate_python("https://example.com/"),
        name="Rafael",
        email="rafael@example.com",
        company="Example Co",
        consent_text="I agree.",
        consented_at=consented_at,
        assessment_id=_ASSESSMENT_ID,
        status=status,
        assigned_owner="Sales",
        next_action="Call prospect",
        next_follow_up_at=consented_at + timedelta(days=1),
    )


def test_engagement_tokens_and_events_are_deterministic(tmp_path: Path) -> None:
    store = EngagementStore(tmp_path)
    link = EngagementLink(
        lead_id="c" * 24,
        assessment_id=_ASSESSMENT_ID,
        kind=EngagementKind.report_open,
    )

    first = store.create_link(link)
    second = store.create_link(link)
    assert first == second == engagement_token(link)
    assert store.load_link(first) == link

    event_id = store.record(
        link,
        occurred_at=datetime(2026, 7, 23, 9, 0, tzinfo=UTC),
        user_agent="browser",
        referrer="https://agency.example/",
    )
    events = store.list_events(lead_id=link.lead_id)
    assert events[0][0] == event_id
    assert events[0][1].kind == EngagementKind.report_open
    assert events[0][1].referrer == "https://agency.example/"


def test_retention_preview_only_selects_terminal_old_leads(tmp_path: Path) -> None:
    now = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
    leads = LeadStore(tmp_path / "leads")
    engagements = EngagementStore(tmp_path / "commercial")
    old_lost_id = leads.save(_lead(consented_at=now - timedelta(days=800), status=LeadStatus.lost))
    leads.save(_lead(consented_at=now - timedelta(days=800), status=LeadStatus.qualified))
    link = EngagementLink(
        lead_id=old_lost_id,
        assessment_id=_ASSESSMENT_ID,
        kind=EngagementKind.report_open,
    )
    old_event_id = engagements.record(link, occurred_at=now - timedelta(days=500))

    preview = retention_preview(
        RetentionPolicy(lead_days=730, engagement_days=365),
        now=now,
        lead_store=leads,
        engagement_store=engagements,
    )
    assert preview.leads == (old_lost_id,)
    assert preview.engagement_events == (old_event_id,)

    apply_retention(preview, lead_store=leads, engagement_store=engagements)
    assert all(identifier != old_lost_id for identifier, _ in leads.list_leads())
    assert engagements.list_events() == []


def test_commercial_summary_uses_persisted_local_evidence(tmp_path: Path) -> None:
    now = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
    leads = LeadStore(tmp_path / "leads")
    engagements = EngagementStore(tmp_path / "commercial")
    lead = _lead(consented_at=now - timedelta(days=2), status=LeadStatus.qualified)
    lead_id = leads.save(lead)
    report = EngagementLink(
        lead_id=lead_id,
        assessment_id=_ASSESSMENT_ID,
        kind=EngagementKind.report_open,
    )
    click = EngagementLink(
        lead_id=lead_id,
        assessment_id=_ASSESSMENT_ID,
        kind=EngagementKind.cta_click,
        destination=TypeAdapter(HttpUrl).validate_python("https://agency.example/contact"),
    )
    engagements.record(report, occurred_at=now - timedelta(hours=2))
    engagements.record(click, occurred_at=now - timedelta(hours=1))

    summary = commercial_summary(
        now=now,
        lead_store=leads,
        engagement_store=engagements,
        webhook_store=LeadDeliveryStore(tmp_path / "webhooks"),
        email_store=EmailAttemptStore(tmp_path / "emails"),
    )
    assert summary.leads_total == 1
    assert summary.status_counts == {"qualified": 1}
    assert summary.owner_counts == {"Sales": 1}
    assert summary.follow_ups_due == 1
    assert summary.report_opens == 1
    assert summary.cta_clicks == 1


def test_commercial_routes_manage_and_track_lead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    form = LeadFormConfig(
        organisation_label="Agency",
        consent_text="I agree.",
        cta_url="https://agency.example/contact",
    )
    form_id = LeadFormStore().save(form)
    lead = _lead(consented_at=datetime(2026, 7, 23, 8, 0, tzinfo=UTC)).model_copy(
        update={"form_id": form_id}
    )
    lead_id = LeadStore().save(AuditLead.model_validate(lead))
    client = TestClient(app)

    dashboard = client.get("/commercial")
    assert dashboard.status_code == 200
    assert "Commercial operations" in dashboard.text
    assert "Rafael" in dashboard.text

    detail = client.get(f"/commercial/leads/{lead_id}")
    assert detail.status_code == 200
    assert "Tracked report URL" in detail.text
    assert "Tracked CTA URL" in detail.text

    links = sorted((tmp_path / "commercial" / "links").glob("*.json"))
    assert len(links) == 2
    report_token = next(
        path.stem
        for path in links
        if '"report_open"' in path.read_text(encoding="utf-8")
    )
    response = client.get(
        f"/engage/{report_token}",
        headers={"user-agent": "test-browser", "referer": "https://agency.example/"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == f"/history/{_ASSESSMENT_ID}"
    events = EngagementStore().list_events(lead_id=lead_id)
    assert len(events) == 1
    assert events[0][1].user_agent == "test-browser"

    updated = client.post(
        f"/commercial/leads/{lead_id}",
        data={
            "status": "qualified",
            "assigned_owner": "Rafael",
            "next_action": "Prepare proposal",
            "notes": "Interested",
            "last_contacted_at": "2026-07-23T09:00",
            "next_follow_up_at": "2026-07-24T09:00",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303
    new_id = updated.headers["location"].rsplit("/", 1)[-1]
    saved = LeadStore().load_lead(new_id)
    assert saved.status == LeadStatus.qualified
    assert saved.assigned_owner == "Rafael"
    assert saved.next_action == "Prepare proposal"
