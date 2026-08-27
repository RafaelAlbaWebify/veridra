from __future__ import annotations

import json
import zipfile
from pathlib import Path

from veridra.ai_evidence_exchange_review_cli import export_pack, import_pack


def _write_zip(path: Path, files: dict[str, object]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, json.dumps(value))


def _competitive(path: Path) -> None:
    _write_zip(
        path,
        {
            "manifest.json": {"schema_version": 3},
            "local_benchmark.json": {"business_count": 1, "rating_median": 4.8},
            "competitive_context.json": [
                {
                    "business_name": "Clinic4U",
                    "website": "https://www.clinic4u.ie/",
                    "signals": {"rating": 4.8, "review_count": 325},
                }
            ],
        },
    )


def _review_zip(path: Path) -> str:
    review_id = "review:Clinic4U:test-review"
    _write_zip(
        path,
        {
            "manifest.json": {
                "schema_version": 2,
                "generated_at": "2026-08-26T10:27:58+00:00",
                "sampling": {
                    "strategies": ["newest", "lowest", "highest"],
                    "per_strategy_limit": 20,
                },
            },
            "review_evidence.json": [
                {
                    "business_name": "Clinic4U",
                    "website": "https://www.clinic4u.ie/",
                    "source_url": "https://www.google.com/maps/place/test",
                    "google_rating": 4.8,
                    "google_review_count": 325,
                    "statistics": {
                        "sampled_review_velocity_per_month_365d": 4.5,
                        "rating_distribution_sample": {"1": 20, "5": 20},
                        "owner_response_rate_sample": 0.5,
                    },
                    "reviews": [
                        {
                            "evidence_id": review_id,
                            "rating": 5,
                            "text": "Excellent service and friendly staff.",
                            "approximate_review_date": "2026-08-20",
                            "owner_response_present": True,
                            "owner_response_text": "Thank you.",
                            "sample_strategy": "newest",
                            "sample_strategies": ["newest", "highest"],
                        }
                    ],
                }
            ],
        },
    )
    return review_id


def test_export_adds_review_evidence_and_recomputes_safe_statistics(tmp_path: Path) -> None:
    competitive = tmp_path / "VERIDRA_COMPETITIVE_TEST.zip"
    reviews = tmp_path / "VERIDRA_REVIEW_INTELLIGENCE_TEST.zip"
    _competitive(competitive)
    review_id = _review_zip(reviews)

    output = export_pack(
        competitive_input=competitive,
        visual_input=None,
        review_input=reviews,
        output_directory=tmp_path,
    )

    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        evidence_index = json.loads(archive.read("evidence_index.json"))
        payload = json.loads(archive.read("prospects/Clinic4U/review_evidence.json"))
        contract = json.loads(archive.read("AI_RESPONSE_CONTRACT.json"))

    assert manifest["schema_version"] == 2
    assert manifest["review_businesses_matched"] == 1
    assert manifest["review_evidence_items"] == 1
    assert review_id in evidence_index
    assert payload["reviews"][0]["text"] == "Excellent service and friendly staff."
    assert payload["reviews"][0]["owner_response_present"] is True
    assert payload["legacy_source_statistics_ignored"] is True

    safe = payload["sampling_safe_statistics"]
    assert safe["newest_sample"]["sample_size"] == 1
    assert safe["highest_sample"]["sample_size"] == 1
    assert "sampled_review_velocity_per_month_365d" not in safe
    assert "rating_distribution_sample" not in safe
    assert "owner_response_rate_sample" not in safe
    assert safe["population_metrics_suppressed"] == [
        "review_velocity",
        "overall_owner_response_rate",
        "overall_rating_distribution",
    ]
    assert contract["prospect_shape"]["review_themes"][0]["evidence_refs"]
    assert contract["prospect_shape"]["evidence_connections"][0]["evidence_refs"]


def test_import_validates_review_theme_and_connection_refs(tmp_path: Path) -> None:
    competitive = tmp_path / "VERIDRA_COMPETITIVE_TEST.zip"
    reviews = tmp_path / "VERIDRA_REVIEW_INTELLIGENCE_TEST.zip"
    _competitive(competitive)
    review_id = _review_zip(reviews)
    source_export = export_pack(
        competitive_input=competitive,
        visual_input=None,
        review_input=reviews,
        output_directory=tmp_path,
    )
    with zipfile.ZipFile(source_export) as archive:
        source_manifest = json.loads(archive.read("manifest.json"))

    enrichment = tmp_path / "VERIDRA_AI_ENRICHMENT_TEST.zip"
    _write_zip(
        enrichment,
        {
            "manifest.json": {
                "schema_version": 1,
                "exchange_type": "veridra_ai_enrichment",
                "source_export_id": source_manifest["export_id"],
            },
            "enrichment.json": [
                {
                    "business_name": "Clinic4U",
                    "review_themes": [
                        {
                            "theme": "Friendly service",
                            "sentiment": "positive",
                            "evidence_refs": [review_id],
                            "supporting_review_count": 1,
                        },
                        {
                            "theme": "Unsupported theme",
                            "sentiment": "negative",
                            "evidence_refs": ["review:missing"],
                            "supporting_review_count": 1,
                        },
                    ],
                    "evidence_connections": [
                        {
                            "connection": "Customer praise is directly supported by review evidence.",
                            "evidence_refs": [review_id],
                            "confidence": "high",
                        }
                    ],
                    "commercial_claims": [],
                }
            ],
        },
    )

    imported = import_pack(
        enrichment_input=enrichment,
        source_export_input=source_export,
        output_directory=tmp_path,
    )
    with zipfile.ZipFile(imported) as archive:
        report = json.loads(archive.read("validation_report.json"))
        normalized = json.loads(archive.read("normalized_enrichment.json"))

    assert report["review_themes_accepted"] == 1
    assert report["evidence_connections_accepted"] == 1
    assert report["interpretations_rejected"] == 1
    assert len(normalized[0]["validated_review_themes"]) == 1
    assert len(normalized[0]["validated_evidence_connections"]) == 1
    assert normalized[0]["rejected_interpretations"][0]["interpretation_type"] == "review_theme"
