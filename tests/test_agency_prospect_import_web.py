from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_prospect_import_web import router as import_router
from veridra.agency_prospect_web import router as prospect_router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect, ProspectStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_prospect_store import TenantProspectStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="prospect-import-session-01",
        authenticated_at=NOW,
    )


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RequestIdentity]:
    identity = _identity()
    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path

    @app.middleware("http")
    async def bind_identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(import_router)
    app.include_router(prospect_router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    return TestClient(app), identity


def _export(*, status: str = "needs_review") -> str:
    return json.dumps(
        {
            "schema_version": "1.1",
            "exported_at": "2026-08-22T18:00:00+00:00",
            "records": [
                {
                    "business_id": "business-1",
                    "location_id": "location-1",
                    "business_name": "Vigo Dental Clinic",
                    "qualification_status": status,
                    "country_code": "ES",
                    "administrative_area": "Pontevedra",
                    "locality": "Vigo",
                    "postal_area": "36201",
                    "phone": "+34986000000",
                    "website": "https://example.es",
                    "first_observed_at": "2026-08-20T10:00:00+00:00",
                    "last_observed_at": "2026-08-22T17:00:00+00:00",
                }
            ],
        }
    )


def test_import_route_wins_over_dynamic_prospect_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/agency/prospects/import")

    assert response.status_code == 200
    assert "Import existing LEADS records" in response.text
    assert "schema 1.1 JSON export" in response.text


def test_valid_export_imports_into_prospect_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)

    response = client.post(
        "/agency/prospects/import",
        headers={"Origin": ORIGIN},
        data={"payload": _export(status="sent_to_veridra")},
    )

    assert response.status_code == 200
    assert "<strong>1</strong> records processed: 1 created" in response.text
    entries = TenantProspectStore(tmp_path).list(identity)
    assert len(entries) == 1
    _, prospect = entries[0]
    assert prospect.status is ProspectStatus.ready_for_audit
    assert prospect.provider == "leadmap-local"


def test_import_preserves_existing_human_outreach_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    existing = Prospect.model_validate(
        {
            "business_name": "Vigo Dental Clinic",
            "website": "https://example.es",
            "locality": "Vigo",
            "country_code": "ES",
            "contact_name": "Verified owner",
            "contact_email": "owner@example.es",
            "status": ProspectStatus.contacted,
            "human_verified": True,
            "evidence_summary": "Operator reviewed this prospect.",
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    store = TenantProspectStore(tmp_path)
    prospect_id = store.save(identity, existing)

    response = client.post(
        "/agency/prospects/import",
        headers={"Origin": ORIGIN},
        data={"payload": _export(status="new")},
    )

    saved = store.load(identity, store.ref(identity, prospect_id))
    assert response.status_code == 200
    assert "1 safely enriched" in response.text
    assert saved.status is ProspectStatus.contacted
    assert saved.human_verified is True
    assert saved.contact_name == "Verified owner"
    assert saved.contact_email == "owner@example.es"
    assert "Operator reviewed this prospect." in saved.evidence_summary
    assert "Imported from LEADS schema 1.1" in saved.evidence_summary


def test_invalid_schema_is_rejected_without_partial_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    payload = json.loads(_export())
    payload["schema_version"] = "9.9"

    response = client.post(
        "/agency/prospects/import",
        headers={"Origin": ORIGIN},
        data={"payload": json.dumps(payload)},
    )

    assert response.status_code == 400
    assert "Unsupported LEADS export schema version" in response.text
    assert TenantProspectStore(tmp_path).list(identity) == []


def test_import_rejects_missing_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    response = client.post(
        "/agency/prospects/import",
        data={"payload": _export()},
    )

    assert response.status_code == 403
