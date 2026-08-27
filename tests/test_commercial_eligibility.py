from __future__ import annotations

import json
from pathlib import Path

from veridra.commercial_eligibility import (
    CommercialEligibilityStatus,
    gate_opportunity_band,
    load_commercial_eligibility,
)


def test_ineligible_business_is_forced_low() -> None:
    assert (
        gate_opportunity_band("priority", CommercialEligibilityStatus.ineligible)
        == "low"
    )


def test_review_required_blocks_priority_and_high() -> None:
    assert (
        gate_opportunity_band("priority", CommercialEligibilityStatus.review_required)
        == "medium"
    )
    assert (
        gate_opportunity_band("high", CommercialEligibilityStatus.review_required)
        == "medium"
    )
    assert (
        gate_opportunity_band("medium", CommercialEligibilityStatus.review_required)
        == "medium"
    )


def test_eligible_business_keeps_opportunity_band() -> None:
    assert gate_opportunity_band("priority", CommercialEligibilityStatus.eligible) == "priority"
    assert gate_opportunity_band("high", CommercialEligibilityStatus.eligible) == "high"


def test_loader_preserves_reason_and_evidence(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.json"
    path.write_text(
        json.dumps(
            [
                {
                    "business_name": "HSE Dental Clinic, Crumlin",
                    "status": "ineligible",
                    "reason": "Public HSE dental service, not a normal private-business prospect.",
                    "evidence_urls": ["https://www.hse.ie/example"],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = load_commercial_eligibility(path)
    item = result["hse dental clinic, crumlin"]

    assert item.status is CommercialEligibilityStatus.ineligible
    assert "Public HSE" in item.reason
    assert item.evidence_urls == ("https://www.hse.ie/example",)


def test_loader_rejects_non_list(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.json"
    path.write_text("{}", encoding="utf-8")

    try:
        load_commercial_eligibility(path)
    except ValueError as exc:
        assert "JSON list" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
