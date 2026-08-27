from __future__ import annotations

import json
import zipfile
from pathlib import Path

from veridra.gbp_discovery_evidence_cli import _load_discovery_contexts


def test_load_discovery_contexts_keeps_no_website_and_excludes_sponsored(
    tmp_path: Path,
) -> None:
    source = tmp_path / "VERIDRA_DISCOVERY_dentist-in-dublin-ie.zip"
    observations = [
        {
            "query_text": "dentist in Dublin, IE",
            "result_rank": 1,
            "business": {
                "name": "No Website Dental",
                "category": "Dentist",
                "website": None,
                "source_url": "https://www.google.com/maps/place/no-website-dental",
                "rating": 4.8,
                "review_count": 84,
            },
        },
        {
            "query_text": "dentist in Dublin, IE",
            "result_rank": 2,
            "business": {
                "name": "Website Dental",
                "category": "Dentist",
                "website": "https://clinic.example/",
                "source_url": "https://www.google.com/maps/place/website-dental",
                "rating": 4.7,
                "review_count": 120,
            },
        },
        {
            "query_text": "dentist in Dublin, IE",
            "result_rank": 3,
            "business": {
                "name": "Sponsored Dental",
                "category": "Sponsored",
                "website": None,
                "source_url": "https://www.google.com/maps/place/sponsored-dental",
                "rating": 5.0,
                "review_count": 999,
            },
        },
    ]
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("captured_observations.json", json.dumps(observations))

    contexts = _load_discovery_contexts(source)

    assert [item["business_name"] for item in contexts] == [
        "No Website Dental",
        "Website Dental",
    ]
    assert contexts[0]["website"] is None
    assert contexts[0]["signals"] == {"rating": 4.8, "review_count": 84}
    assert contexts[0]["discovery_result_rank"] == 1
