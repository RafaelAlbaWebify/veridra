from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from veridra.leadmap_import import LeadMapImportError, prospects_from_leadmap_export
from veridra.prospect import ProspectStatus

NOW = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)


def _payload(*, schema_version: str = "1.1", qualification_status: str = "shortlisted") -> str:
    return json.dumps(
        {
            "schema_version": schema_version,
            "exported_at": NOW.isoformat(),
            "records": [
                {
                    "business_id": "business-01",
                    "location_id": "location-01",
                    "business_name": "Murphy Roofing Ltd",
                    "qualification_status": qualification_status,
                    "country_code": "ie",
                    "administrative_area": "Cork",
                    "locality": "Cork",
                    "postal_area": "",
                    "phone": "+353000000000",
                    "website": "https://example.ie",
                    "first_observed_at": NOW.isoformat(),
                    "last_observed_at": NOW.isoformat(),
                }
            ],
        }
    )


def test_import_preserves_leadmap_identity_and_observation_evidence() -> None:
    prospects = prospects_from_leadmap_export(_payload())

    assert len(prospects) == 1
    prospect = prospects[0]
    assert prospect.business_name == "Murphy Roofing Ltd"
    assert str(prospect.website) == "https://example.ie/"
    assert prospect.country_code == "IE"
    assert prospect.provider == "leadmap-local"
    assert prospect.provider_key == "business-01:location-01"
    assert prospect.status is ProspectStatus.shortlisted
    assert prospect.qualification is None
    assert "schema 1.1" in prospect.evidence_summary


def test_old_handoff_states_collapse_into_single_veridra_lifecycle() -> None:
    ready = prospects_from_leadmap_export(
        _payload(qualification_status="sent_to_veridra")
    )[0]
    reviewed = prospects_from_leadmap_export(
        _payload(qualification_status="veridra_reviewed")
    )[0]

    assert ready.status is ProspectStatus.ready_for_audit
    assert reviewed.status is ProspectStatus.audited


def test_unknown_legacy_status_requires_review_instead_of_guessing() -> None:
    prospect = prospects_from_leadmap_export(
        _payload(qualification_status="future_status")
    )[0]

    assert prospect.status is ProspectStatus.needs_review


def test_import_rejects_unknown_export_schema() -> None:
    with pytest.raises(LeadMapImportError, match="Unsupported LEADS export schema"):
        prospects_from_leadmap_export(_payload(schema_version="2.0"))
