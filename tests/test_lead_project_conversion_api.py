from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import HttpUrl
from starlette.requests import Request

from veridra.core import demo_assessment
from veridra.history import HistoryStore
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_project_conversion_api import (
    LeadProjectConversion,
    convert_lead_to_project,
)
from veridra.lead_project_link_store import LeadProjectLinkStore
from veridra.lead_store import AuditLead, LeadFormConfig, LeadStatus
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_lead_form_store import TenantLeadFormStore
from veridra.tenant_lead_store import TenantLeadStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 13, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="lead-project-conversion-01",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="lead-project-viewer-0001",
    authenticated_at=NOW,
)


def _request(root: Path) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/tenant/leads/test/convert-project",
            "headers": [],
            "app": app,
        }
    )


def _lead_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, str]:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    root = tmp_path / "tenants"
    assessment = demo_assessment().model_copy(update={"target": "https://example.com/"})
    assessment_id = HistoryStore().save(assessment)
    form_id = TenantLeadFormStore(root).save(
        OWNER,
        LeadFormConfig(
            organisation_label="Agency",
            consent_text="I agree to be contacted.",
        ),
    )
    lead = AuditLead(
        form_id=form_id,
        website=HttpUrl("https://example.com/"),
        name="Alex Client",
        email="alex@example.com",
        company="Client Co",
        consent_text="I agree to be contacted.",
        consented_at=NOW,
        assessment_id=assessment_id,
    )
    lead_id = TenantLeadStore(root).save(OWNER, lead)
    return root, lead_id, assessment_id


def test_lead_conversion_creates_project_and_marks_lead_won(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, lead_id, source_assessment_id = _lead_fixture(tmp_path, monkeypatch)

    created = convert_lead_to_project(
        lead_id,
        LeadProjectConversion(project_name="Client website", client_label="Client Co"),
        _request(root),
        OWNER,
    )

    assert created.lead_id == lead_id
    assert created.existing is False
    project = TenantProjectStore(root).load(
        OWNER,
        TenantProjectStore(root).ref(OWNER, created.project_id),
    )
    assert project.target_url == "https://example.com/"
    saved = TenantHistoryStore(root).load(
        OWNER,
        TenantHistoryStore(root).ref(OWNER, created.project_id, created.assessment_id),
    )
    assert str(saved.target) == "https://example.com/"
    assert source_assessment_id == created.assessment_id
    lead = TenantLeadStore(root).load(
        OWNER,
        TenantLeadStore(root).ref(OWNER, lead_id),
    )
    assert lead.status == LeadStatus.won


def test_lead_conversion_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, lead_id, _ = _lead_fixture(tmp_path, monkeypatch)
    payload = LeadProjectConversion(project_name="Client website", client_label="Client Co")

    first = convert_lead_to_project(lead_id, payload, _request(root), OWNER)
    second = convert_lead_to_project(lead_id, payload, _request(root), OWNER)

    assert second.existing is True
    assert second.project_id == first.project_id
    assert second.assessment_id == first.assessment_id
    links = LeadProjectLinkStore(root / OWNER.tenant_id / "lead-project-links")
    assert links.load(lead_id) is not None
    assert len(TenantProjectStore(root).list(OWNER)) == 1


def test_viewer_cannot_convert_lead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, lead_id, _ = _lead_fixture(tmp_path, monkeypatch)

    with pytest.raises(HTTPException) as captured:
        convert_lead_to_project(
            lead_id,
            LeadProjectConversion(project_name="Forbidden"),
            _request(root),
            VIEWER,
        )

    assert captured.value.status_code == 403


def test_missing_source_assessment_is_concealed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, lead_id, assessment_id = _lead_fixture(tmp_path, monkeypatch)
    HistoryStore().delete(assessment_id)

    with pytest.raises(HTTPException) as captured:
        convert_lead_to_project(
            lead_id,
            LeadProjectConversion(project_name="Client website"),
            _request(root),
            OWNER,
        )

    assert captured.value.status_code == 404
    assert captured.value.detail == "Lead conversion source not found."
