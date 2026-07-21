from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import veridra.lead_web as lead_web
from veridra.core import demo_assessment
from veridra.lead_store import LeadFormConfig, LeadFormStore, LeadStatus, LeadStore
from veridra.runtime import app

client = TestClient(app)


def _saved_form(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides: object) -> str:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    values: dict[str, object] = {
        "organisation_label": "Agency <One>",
        "heading": "Free audit",
        "consent_text": "I agree to be contacted about this audit.",
    }
    values.update(overrides)
    return LeadFormStore().save(LeadFormConfig(**values))


def test_public_form_is_isolated_and_submission_captures_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    form_id = _saved_form(tmp_path, monkeypatch, collect_phone=True)
    monkeypatch.setattr(lead_web, "assess_url", lambda _url: demo_assessment())
    lead_web._RATE_BUCKETS.clear()

    page = client.get(f"/embed/audit/{form_id}")
    assert page.status_code == 200
    assert "Agency &lt;One&gt;" in page.text
    assert "/projects" not in page.text
    assert "/lead-forms" not in page.text
    assert "/leads" not in page.text

    missing_consent = client.post(
        f"/embed/audit/{form_id}",
        data={
            "website": "example.com",
            "name": "Rafael",
            "email": "rafael@example.com",
        },
    )
    assert missing_consent.status_code == 400

    submitted = client.post(
        f"/embed/audit/{form_id}",
        data={
            "website": "example.com",
            "name": "Rafael <Alba>",
            "email": "rafael@example.com",
            "phone": "+34 600 000 000",
            "consent": "yes",
        },
    )
    assert submitted.status_code == 200
    assert "Rafael &lt;Alba&gt;" in submitted.text
    assert "Your website assessment is ready" in submitted.text

    leads = LeadStore().list_leads(form_id=form_id)
    assert len(leads) == 1
    _, lead = leads[0]
    assert lead.consent_text == "I agree to be contacted about this audit."
    assert lead.phone == "+34 600 000 000"
    assert lead.status == LeadStatus.new


def test_origin_restriction_and_rate_limit_are_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    form_id = _saved_form(
        tmp_path,
        monkeypatch,
        allowed_origins=("https://agency.example",),
    )
    monkeypatch.setattr(lead_web, "assess_url", lambda _url: demo_assessment())
    lead_web._RATE_BUCKETS.clear()

    blocked = client.get(
        f"/embed/audit/{form_id}", headers={"Origin": "https://other.example"}
    )
    assert blocked.status_code == 403

    allowed = client.get(
        f"/embed/audit/{form_id}", headers={"Origin": "https://agency.example"}
    )
    assert allowed.status_code == 200

    for index in range(lead_web._RATE_LIMIT):
        response = client.post(
            f"/embed/audit/{form_id}",
            headers={"Origin": "https://agency.example"},
            data={
                "website": "example.com",
                "name": f"Lead {index}",
                "email": f"lead{index}@example.com",
                "consent": "yes",
            },
        )
        assert response.status_code == 200

    limited = client.post(
        f"/embed/audit/{form_id}",
        headers={"Origin": "https://agency.example"},
        data={
            "website": "example.com",
            "name": "Extra",
            "email": "extra@example.com",
            "consent": "yes",
        },
    )
    assert limited.status_code == 429


def test_lead_management_updates_exports_and_deletes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    form_id = _saved_form(tmp_path, monkeypatch)
    monkeypatch.setattr(lead_web, "assess_url", lambda _url: demo_assessment())
    lead_web._RATE_BUCKETS.clear()
    created = client.post(
        f"/embed/audit/{form_id}",
        data={
            "website": "example.com",
            "name": "Rafael",
            "email": "rafael@example.com",
            "company": "Webify, Ltd",
            "consent": "yes",
        },
    )
    assert created.status_code == 200
    lead_id, _ = LeadStore().list_leads()[0]

    detail = client.get(f"/leads/{lead_id}")
    assert detail.status_code == 200
    assert "rafael@example.com" in detail.text

    updated = client.post(
        f"/leads/{lead_id}/edit",
        data={"status": LeadStatus.qualified.value, "notes": "Promising <lead>"},
        follow_redirects=False,
    )
    assert updated.status_code == 303
    new_id = updated.headers["location"].rsplit("/", 1)[1]
    lead = LeadStore().load_lead(new_id)
    assert lead.status == LeadStatus.qualified
    assert lead.notes == "Promising <lead>"

    filtered = client.get("/leads", params={"status": LeadStatus.qualified.value})
    assert filtered.status_code == 200
    assert "rafael@example.com" in filtered.text

    exported = client.get("/leads.csv")
    assert exported.status_code == 200
    assert "Webify, Ltd" in exported.text
    assert exported.headers["content-type"].startswith("text/csv")

    deleted = client.post(f"/leads/{new_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert LeadStore().list_leads() == []


def test_local_form_configuration_route_validates_and_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))

    invalid = client.post(
        "/lead-forms",
        data={"organisation_label": "Agency", "consent_text": ""},
    )
    assert invalid.status_code == 400

    created = client.post(
        "/lead-forms",
        data={
            "organisation_label": "Agency",
            "heading": "Website report",
            "submit_label": "Run audit",
            "consent_text": "I consent to contact.",
            "allowed_origins": "https://agency.example/path",
            "collect_company": "on",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    form_id = created.headers["location"].rsplit("/", 1)[1]
    config = LeadFormStore().load_form(form_id)
    assert config.allowed_origins == ("https://agency.example",)
    assert config.collect_company is True
