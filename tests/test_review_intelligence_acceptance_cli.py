from __future__ import annotations

import json
import zipfile
from pathlib import Path

from veridra.review_intelligence_acceptance_cli import validate_review_intelligence


def _write_review_pack(path: Path) -> None:
    reviews = [
        {
            "evidence_id": "review:example:1",
            "rating": 5,
            "approximate_review_date": "2026-08-31",
            "approximate_owner_response_date": None,
            "owner_response_present": False,
            "sample_strategy": "newest",
            "sample_strategies": ["newest", "highest"],
        },
        {
            "evidence_id": "review:example:2",
            "rating": 2,
            "approximate_review_date": "2026-08-01",
            "approximate_owner_response_date": "2026-08-02",
            "owner_response_present": True,
            "sample_strategy": "lowest",
            "sample_strategies": ["lowest"],
        },
    ]
    manifest = {
        "review_evidence_items": 2,
        "sampling": {"per_strategy_limit": 5, "strategies": ["newest", "lowest", "highest"]},
        "interpretation": "none",
        "persistence": "none",
        "outreach": "none",
    }
    evidence = [
        {
            "business_name": "Example Dental",
            "reviews": reviews,
        }
    ]
    index = {
        "review:example:1": {"type": "google_review"},
        "review:example:2": {"type": "google_review"},
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("review_evidence.json", json.dumps(evidence))
        archive.writestr("evidence_index.json", json.dumps(index))


def _write_ai_export(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "evidence_index.json",
            json.dumps(
                {
                    "review:example:1": {
                        "type": "google_review",
                        "business_name": "Example Dental",
                    }
                }
            ),
        )


def test_acceptance_passes_valid_review_pack(tmp_path: Path) -> None:
    review_pack = tmp_path / "VERIDRA_REVIEW_INTELLIGENCE_test.zip"
    _write_review_pack(review_pack)

    report = validate_review_intelligence(review_pack)

    assert report["passed"] is True
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks["nonzero_review_evidence"] is True
    assert checks["sampling_bounded"] is True
    assert checks["ai_export_contains_traceable_review_evidence"] is None


def test_acceptance_can_verify_ai_export_integration(tmp_path: Path) -> None:
    review_pack = tmp_path / "VERIDRA_REVIEW_INTELLIGENCE_test.zip"
    ai_export = tmp_path / "VERIDRA_AI_EXPORT_test.zip"
    _write_review_pack(review_pack)
    _write_ai_export(ai_export)

    report = validate_review_intelligence(review_pack, ai_export=ai_export)

    assert report["passed"] is True
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks["ai_export_contains_traceable_review_evidence"] is True


def test_acceptance_rejects_zero_evidence(tmp_path: Path) -> None:
    review_pack = tmp_path / "VERIDRA_REVIEW_INTELLIGENCE_empty.zip"
    with zipfile.ZipFile(review_pack, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"review_evidence_items": 0, "sampling": {"per_strategy_limit": 5}}),
        )
        archive.writestr("review_evidence.json", json.dumps([]))
        archive.writestr("evidence_index.json", json.dumps({}))

    report = validate_review_intelligence(review_pack)

    assert report["passed"] is False
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks["nonzero_review_evidence"] is False
    assert checks["business_with_nonempty_sample"] is False


def test_acceptance_rejects_interpretation_fields(tmp_path: Path) -> None:
    review_pack = tmp_path / "VERIDRA_REVIEW_INTELLIGENCE_interpreted.zip"
    _write_review_pack(review_pack)
    with zipfile.ZipFile(review_pack, "a") as archive:
        archive.writestr(
            "review_evidence.json",
            json.dumps(
                [
                    {
                        "business_name": "Example Dental",
                        "reviews": [
                            {
                                "evidence_id": "review:example:1",
                                "rating": 5,
                                "sentiment": "positive",
                                "sample_strategy": "newest",
                                "sample_strategies": ["newest"],
                            }
                        ],
                    }
                ]
            ),
        )

    report = validate_review_intelligence(review_pack)

    assert report["passed"] is False
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks["no_deterministic_interpretation_fields"] is False
