from __future__ import annotations

import csv
import io

from veridra.agency_prospect_discovery_evidence_web import (
    _csv_bytes,
    _safe_filename,
    _summary_markdown,
)


def _observation() -> dict[str, object]:
    return {
        "query_text": "dentist in Dublin, IE",
        "query_sequence": 1,
        "result_rank": 2,
        "first_seen_scroll_step": 0,
        "business": {
            "provider": "assisted-google-maps",
            "provider_key": "google-maps:test",
            "name": "Slievemore Dental",
            "category": "Emergency dental service",
            "locality": "Dublin",
            "administrative_area": "Dublin",
            "country_code": "IE",
            "website": "https://www.slievemoredental.ie/",
            "source_url": "https://www.google.com/maps/place/Slievemore+Dental/",
            "observed_at": "2026-08-24T02:00:00Z",
        },
    }


def test_safe_filename_is_bounded_and_portable() -> None:
    assert _safe_filename("dentist in Dublin, IE") == "dentist-in-Dublin-IE"
    assert _safe_filename("***") == "discovery"
    assert len(_safe_filename("x" * 200)) == 80


def test_csv_export_contains_actual_capture_fields() -> None:
    content = _csv_bytes([_observation()]).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(content)))

    assert len(rows) == 1
    assert rows[0]["result_rank"] == "2"
    assert rows[0]["name"] == "Slievemore Dental"
    assert rows[0]["category"] == "Emergency dental service"
    assert rows[0]["website"] == "https://www.slievemoredental.ie/"
    assert rows[0]["country_code"] == "IE"


def test_summary_distinguishes_missing_capture_from_missing_business_fact() -> None:
    missing = _observation()
    raw_business = missing["business"]
    assert isinstance(raw_business, dict)
    business = dict(raw_business)
    business["website"] = None
    missing["business"] = business

    summary = _summary_markdown(
        session_id="session-1",
        query_text="dentist in Dublin, IE",
        observations=[missing],
        generated_at="2026-08-24T02:00:00+00:00",
    )

    assert "Website captured: **0**" in summary
    assert "not captured" in summary
    assert "No website" not in summary
    assert "nothing in this ZIP generation is persisted" in summary
