from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime

from veridra.assisted_discovery import (
    TraversalObservation,
    TraversalProgress,
    TraversalResult,
    TraversalStopReason,
)
from veridra.automated_discovery_evidence_cli import _build_archive
from veridra.prospect_discovery import ObservedBusiness


def _result() -> TraversalResult:
    with_website = ObservedBusiness.model_validate(
        {
            "provider": "assisted-google-maps",
            "provider_key": "google-maps:test-website",
            "name": "Slievemore Dental",
            "category": "Emergency dental service",
            "locality": "Dublin",
            "administrative_area": "Dublin",
            "country_code": "IE",
            "website": "https://www.slievemoredental.ie/",
            "source_url": "https://www.google.com/maps/place/Slievemore+Dental/",
            "observed_at": datetime(2026, 8, 24, tzinfo=UTC),
        }
    )
    without_website = ObservedBusiness.model_validate(
        {
            "provider": "assisted-google-maps",
            "provider_key": "google-maps:test-no-website",
            "name": "No Website Dental",
            "category": "Dentist",
            "locality": "Dublin",
            "administrative_area": "Dublin",
            "country_code": "IE",
            "website": None,
            "source_url": "https://www.google.com/maps/place/No+Website+Dental/",
            "rating": 4.8,
            "review_count": 84,
            "observed_at": datetime(2026, 8, 24, tzinfo=UTC),
        }
    )
    return TraversalResult(
        observations=(
            TraversalObservation(
                business=with_website,
                query_text="dentist in Dublin, IE",
                query_sequence=1,
                result_rank=1,
                first_seen_scroll_step=0,
            ),
            TraversalObservation(
                business=without_website,
                query_text="dentist in Dublin, IE",
                query_sequence=1,
                result_rank=2,
                first_seen_scroll_step=0,
            ),
        ),
        progress=TraversalProgress(
            query_text="dentist in Dublin, IE",
            query_sequence=1,
            scroll_step=0,
            unique_results=2,
            stagnant_scrolls=0,
            elapsed_seconds=1.2,
            stop_reason=TraversalStopReason.max_results,
        ),
    )


def test_build_archive_contains_capture_and_ingest_preview() -> None:
    payload = _build_archive(
        result=_result(),
        query_text="dentist in Dublin, IE",
        generated_at="2026-08-24T02:00:00+00:00",
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "README.md",
            "captured_businesses.csv",
            "captured_observations.json",
            "ingest_preview.json",
            "manifest.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        captured = json.loads(archive.read("captured_observations.json"))
        preview = json.loads(archive.read("ingest_preview.json"))

    assert manifest["captured_count"] == 2
    assert manifest["website_captured_count"] == 1
    assert manifest["no_website_captured_count"] == 1
    assert manifest["ingest_preview_count"] == 2
    assert manifest["persistence"] == "none"
    assert manifest["execution"] == "automated-local-backend"
    assert captured[0]["business"]["website"] == "https://www.slievemoredental.ie/"
    assert captured[1]["business"]["website"] is None
    assert preview[0]["prospect"]["website"] == "https://www.slievemoredental.ie/"
    assert preview[1]["prospect"]["website"] is None
