# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from veridra.agency_lead_web import router
from veridra.core import demo_assessment
from veridra.history import HistoryStore
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_project_link_store import LeadProjectLink, LeadProjectLinkStore
from veridra.lead_store import AuditLead, LeadFormConfig, LeadStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_lead_form_store import TenantLeadFormStore
from veridra.tenant_lead_store import TenantLeadStore

NOW = datetime(2026, 7, 27, 14, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="agency-lead-owner-000001",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="agency-lead-viewer-000001",
    authenticated_at=NOW,
)


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str]:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    root = tmp_path / "tenants"
    assessment = demo_assessment().model_copy(update={"target": "https://example.com/"})
    assessment_id = HistoryStore().save(assessment)
    form_id = TenantLeadFormStore(root).save(
        OWNER,
        LeadFormConfig(organisation_label="Agency", consent_text="Consent"),
    )
    lead_id = TenantLeadStore(root).save(
        OWNER,
        AuditLead(
            form_id=form_id,
            website=HttpUrl("https://example.com/"),
            name="Alex <Client>",
            email="alex@example.com",
            company="Client Co",
            consent_text="Consent",
            consented_at=NOW,
            assessment_id=assessment_id,
        ),
    )
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "owner":
            bind_verified_request_identity(request, OWNER)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), lead_id


def test_lead_inbox_requires_identity_and_escapes_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lead_id = _client(tmp_path, monkeypatch)

    anonymous = client.get("/agency/leads")
    response = client.get("/agency/leads", headers={"x-test-role": "owner"})

    assert anonymous.status_code == 401
    assert response.status_code == 200
    assert "Alex &lt;Client&gt;" in response.text
    assert "Alex <Client>" not in response.text
    assert f"/agency/leads/{lead_id}" in response.text
    assert f"/agency/leads/{lead_id}/convert" in response.text
    assert "aria-label='Agency navigation'" in response.text
    assert "href='/agency/leads' aria-current='page'" in response.text
    assert "href='/agency/projects'" in response.text
    assert "href='/workspace'" in response.text
    assert "href='/workspace/members'" in response.text
    assert "<a href='/agency'>Agency home</a>" in response.text


def test_viewer_cannot_open_lead_inbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/agency/leads", headers={"x-test-role": "viewer"})

    assert response.status_code == 403


def test_lead_detail_exposes_qualification_fields_and_denies_viewer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lead_id = _client(tmp_path, monkeypatch)

    viewer = client.get(
        f"/agency/leads/{lead_id}",
        headers={"x-test-role": "viewer"},
    )
    owner = client.get(
        f"/agency/leads/{lead_id}",
        headers={"x-test-role": "owner"},
    )

    assert viewer.status_code == 403
    assert owner.status_code == 200
    assert "Alex &lt;Client&gt;" in owner.text
    assert "Qualification and follow-up" in owner.text
    assert "name='status'" in owner.text
    assert "name='assigned_owner'" in owner.text
    assert "name='next_action'" in owner.text
    assert "name='next_follow_up_at'" in owner.text
    assert "name='notes'" in owner.text
    assert f"/agency/leads/{lead_id}/convert" in owner.text


def test_lead_update_preserves_id_and_qualification_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lead_id = _client(tmp_path, monkeypatch)
    root = tmp_path / "tenants"

    response = client.post(
        f"/agency/leads/{lead_id}",
        headers={"x-test-role": "owner"},
        data={
            "status": "qualified",
            "assigned_owner": "Rafael",
            "last_contacted_at": "2026-08-20T10:30",
            "next_follow_up_at": "2026-08-22T09:00",
            "next_action": "Send proposal",
            "notes": "Qualified after discovery call.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/agency/leads/{lead_id}"
    entries = TenantLeadStore(root).list(OWNER)
    assert [entry_id for entry_id, _ in entries] == [lead_id]
    lead = entries[0][1]
    assert lead.status == LeadStatus.qualified
    assert lead.assigned_owner == "Rafael"
    assert lead.next_action == "Send proposal"
    assert lead.notes == "Qualified after discovery call."
    assert lead.last_contacted_at is not None
    assert lead.next_follow_up_at is not None
    assert lead.last_contacted_at.isoformat().startswith("2026-08-20T10:30")
    assert lead.next_follow_up_at.isoformat().startswith("2026-08-22T09:00")


def test_invalid_lead_update_is_rejected_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lead_id = _client(tmp_path, monkeypatch)
    root = tmp_path / "tenants"
    store = TenantLeadStore(root)
    before = store.load(OWNER, store.ref(OWNER, lead_id))

    response = client.post(
        f"/agency/leads/{lead_id}",
        headers={"x-test-role": "owner"},
        data={"status": "not-a-status", "notes": "Should not save"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert store.load(OWNER, store.ref(OWNER, lead_id)) == before


def test_lead_delete_removes_tenant_lead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lead_id = _client(tmp_path, monkeypatch)
    root = tmp_path / "tenants"

    response = client.post(
        f"/agency/leads/{lead_id}/delete",
        headers={"x-test-role": "owner"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/agency/leads"
    assert TenantLeadStore(root).list(OWNER) == []


def test_confirmation_is_read_only_and_viewer_is_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lead_id = _client(tmp_path, monkeypatch)
    root = tmp_path / "tenants"
    lead_path = root / OWNER.tenant_id / "leads" / f"{lead_id}.json"
    before = lead_path.read_bytes()

    viewer = client.get(
        f"/agency/leads/{lead_id}/convert",
        headers={"x-test-role": "viewer"},
    )
    owner = client.get(
        f"/agency/leads/{lead_id}/convert",
        headers={"x-test-role": "owner"},
    )

    assert viewer.status_code == 403
    assert owner.status_code == 200
    assert "aria-label='Agency navigation'" in owner.text
    assert "href='/agency/leads' aria-current='page'" in owner.text
    assert "<a href='/agency'>Agency home</a>" in owner.text
    assert "<a href='/agency/leads'>Audit leads</a>" in owner.text
    assert f"<a href='/agency/leads/{lead_id}'>Lead detail</a>" in owner.text
    assert lead_path.read_bytes() == before
    assert not (root / OWNER.tenant_id / "lead-project-links").exists()


def test_submit_converts_and_redirects_to_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lead_id = _client(tmp_path, monkeypatch)

    response = client.post(
        f"/agency/leads/{lead_id}/convert",
        headers={"x-test-role": "owner"},
        data={"project_name": "Client website", "client_label": "Client Co"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/agency/projects/")
    link = LeadProjectLinkStore(
        tmp_path / "tenants" / OWNER.tenant_id / "lead-project-links"
    ).load(lead_id)
    assert link is not None


def test_existing_conversion_opens_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lead_id = _client(tmp_path, monkeypatch)
    store = LeadProjectLinkStore(
        tmp_path / "tenants" / OWNER.tenant_id / "lead-project-links"
    )
    store.save(
        LeadProjectLink(
            lead_id=lead_id,
            project_id="b" * 24,
            assessment_id="c" * 24,
        )
    )

    inbox = client.get("/agency/leads", headers={"x-test-role": "owner"})
    detail = client.get(
        f"/agency/leads/{lead_id}",
        headers={"x-test-role": "owner"},
    )
    confirmation = client.get(
        f"/agency/leads/{lead_id}/convert",
        headers={"x-test-role": "owner"},
        follow_redirects=False,
    )

    assert f"/agency/projects/{'b' * 24}" in inbox.text
    assert f"/agency/projects/{'b' * 24}" in detail.text
    assert confirmation.status_code == 303
    assert confirmation.headers["location"] == f"/agency/projects/{'b' * 24}"
