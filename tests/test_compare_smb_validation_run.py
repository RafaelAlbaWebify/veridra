from __future__ import annotations

import json
import zipfile
from pathlib import Path

from veridra.smb_validation_compare import compare


def _assessment(findings: list[dict[str, object]]) -> dict[str, object]:
    return {"findings": findings}


def test_compare_scores_positive_negative_and_blocked_expectations(tmp_path: Path) -> None:
    archive_path = tmp_path / "audits.zip"
    ranking = [
        {"result_rank": 1, "name": "Alpha Dental", "audit_status": "success"},
        {"result_rank": 2, "name": "Beta Dental", "audit_status": "success"},
        {"result_rank": 3, "name": "Blocked Dental", "audit_status": "failed"},
    ]
    alpha = _assessment(
        [
            {
                "id": "content.placeholder-default",
                "status": "attention",
                "evidence": {
                    "affected_pages": [
                        {
                            "url": "https://alpha.example/sample-page",
                            "pattern": "wordpress_sample_page",
                        }
                    ]
                },
            }
        ]
    )
    beta = _assessment(
        [
            {
                "id": "content.explicit-update-age",
                "status": "passed",
                "evidence": {"indicators": []},
            }
        ]
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"business_targets": 3}))
        archive.writestr("audit_ranking.json", json.dumps(ranking))
        archive.writestr("assessments/01-Alpha-Dental.json", json.dumps(alpha))
        archive.writestr("assessments/02-Beta-Dental.json", json.dumps(beta))

    expectations = {
        "expectations": [
            {
                "id": "alpha-sample",
                "business_name": "Alpha Dental",
                "kind": "positive",
                "finding_id": "content.placeholder-default",
                "evidence_collection": "affected_pages",
                "evidence_url": "https://alpha.example/sample-page/",
                "evidence_pattern": "wordpress_sample_page",
            },
            {
                "id": "beta-negative",
                "business_name": "Beta Dental",
                "kind": "negative",
                "finding_id": "content.explicit-update-age",
            },
            {
                "id": "blocked-positive",
                "business_name": "Blocked Dental",
                "kind": "positive",
                "finding_id": "content.explicit-update-age",
            },
        ]
    }
    expectations_path = tmp_path / "expectations.json"
    expectations_path.write_text(json.dumps(expectations), encoding="utf-8")

    result = compare(archive_path, expectations_path)

    assert result["positive_evaluable"] == 1
    assert result["positive_hits"] == 1
    assert result["strict_positive_recall"] == 1.0
    assert result["negative_evaluable"] == 1
    assert result["negative_passes"] == 1
    assert result["negative_control_pass_rate"] == 1.0
    assert result["current_positive_recall"] == 1.0
    assert result["current_negative_control_pass_rate"] == 1.0
    blocked = result["expectations"][2]
    assert blocked["evaluable"] is False
    assert blocked["blocked_by_acquisition"] is True


def test_compare_matches_conflict_url_in_either_side(tmp_path: Path) -> None:
    archive_path = tmp_path / "audits.zip"
    ranking = [{"result_rank": 1, "name": "Crown", "audit_status": "success"}]
    assessment = _assessment(
        [
            {
                "id": "content.opening-hours-consistency",
                "status": "attention",
                "evidence": {
                    "conflicts": [
                        {
                            "first_url": "https://crown.example/",
                            "second_url": "https://crown.example/contact-us/",
                            "differences": [{"day": "monday"}],
                        }
                    ]
                },
            }
        ]
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("audit_ranking.json", json.dumps(ranking))
        archive.writestr("assessments/01-Crown.json", json.dumps(assessment))

    expectations_path = tmp_path / "expectations.json"
    expectations_path.write_text(
        json.dumps(
            {
                "expectations": [
                    {
                        "id": "hours",
                        "business_name": "Crown",
                        "kind": "positive",
                        "finding_id": "content.opening-hours-consistency",
                        "evidence_collection": "conflicts",
                        "evidence_url": "https://crown.example/contact-us",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = compare(archive_path, expectations_path)
    assert result["positive_hits"] == 1


def test_compare_preserves_frozen_score_and_excludes_site_drift_from_current_metric(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "audits.zip"
    ranking = [{"result_rank": 1, "name": "Dublin", "audit_status": "success"}]
    assessment = _assessment(
        [
            {
                "id": "content.placeholder-default",
                "status": "passed",
                "evidence": {"affected_pages": []},
            }
        ]
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("audit_ranking.json", json.dumps(ranking))
        archive.writestr("assessments/01-Dublin.json", json.dumps(assessment))

    expectations_path = tmp_path / "expectations.json"
    expectations_path.write_text(
        json.dumps(
            {
                "expectations": [
                    {
                        "id": "dublin-phone",
                        "business_name": "Dublin",
                        "kind": "positive",
                        "finding_id": "content.placeholder-default",
                        "evidence_collection": "affected_pages",
                        "evidence_url": "https://dublin.example/",
                        "evidence_pattern": "literal_phone_placeholder",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    adjudications_path = tmp_path / "adjudications.json"
    adjudications_path.write_text(
        json.dumps(
            {
                "adjudications": [
                    {
                        "expectation_id": "dublin-phone",
                        "status": "site_drift",
                        "exclude_from_current_metric": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = compare(archive_path, expectations_path, adjudications_path)

    assert result["positive_evaluable"] == 1
    assert result["positive_hits"] == 0
    assert result["strict_positive_recall"] == 0.0
    assert result["current_positive_evaluable"] == 0
    assert result["current_positive_hits"] == 0
    assert result["current_positive_recall"] is None
    assert result["adjudications_applied"] == 1
    row = result["expectations"][0]
    assert row["excluded_from_current_metric"] is True
    assert row["adjudication"]["status"] == "site_drift"
