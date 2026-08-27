from __future__ import annotations

import json
import zipfile
from pathlib import Path

from veridra.gbp_market_evidence_cli import _load_market_contexts


def test_market_context_loader_preserves_no_website_and_query_provenance(tmp_path: Path) -> None:
    source = tmp_path / "VERIDRA_MARKET_ENUMERATION_test.zip"
    payload = [
        {
            "business": {
                "provider": "assisted-google-maps",
                "provider_key": "google-maps:one",
                "name": "No Website Dental",
                "category": "Dentist",
                "locality": "Dublin",
                "administrative_area": "Dublin",
                "country_code": "IE",
                "website": None,
                "source_url": "https://www.google.com/maps/place/no-website-dental",
                "rating": 4.8,
                "review_count": 57,
                "profile_photo_signal_count": 2,
            },
            "first_query_text": "dentist in Dublin 12, IE",
            "first_query_sequence": 13,
            "first_result_rank": 7,
            "seen_in_queries": [
                "dentist in Dublin 12, IE",
                "family dentist in Dublin, IE",
            ],
            "observation_count": 2,
        }
    ]
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("market_businesses.json", json.dumps(payload))

    contexts = _load_market_contexts(source)

    assert len(contexts) == 1
    context = contexts[0]
    assert context["business_name"] == "No Website Dental"
    assert context["website"] is None
    assert context["provider_key"] == "google-maps:one"
    assert context["first_query_sequence"] == 13
    assert context["first_result_rank"] == 7
    assert context["observation_count"] == 2
    assert context["seen_in_queries"] == [
        "dentist in Dublin 12, IE",
        "family dentist in Dublin, IE",
    ]
    assert context["signals"] == {"rating": 4.8, "review_count": 57}


def test_market_context_loader_skips_rows_without_maps_source(tmp_path: Path) -> None:
    source = tmp_path / "VERIDRA_MARKET_ENUMERATION_test.zip"
    payload = [
        {
            "business": {
                "provider_key": "google-maps:missing",
                "name": "Missing Source",
                "category": "Dentist",
                "source_url": None,
            },
            "seen_in_queries": ["dentist in Dublin, IE"],
        }
    ]
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("market_businesses.json", json.dumps(payload))

    assert _load_market_contexts(source) == []
