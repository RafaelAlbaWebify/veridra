from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from veridra.ai_review_exchange import (
    AIReviewBundle,
    AIReviewExchangeError,
    DeterministicScore,
    EvidenceItem,
    ReviewContextType,
    build_review_bundle,
    parse_and_validate_result,
    result_integrity_hash,
)

BASE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _bundle() -> AIReviewBundle:
    return build_review_bundle(
        context_type=ReviewContextType.project,
        context_id="abc123",
        context_label="Example delivery",
        target="https://example.com/",
        context={"client": "Example", "assessment_id": "assessment-1"},
        deterministic_scores=(
            DeterministicScore(
                key="finding_count",
                value=2,
                basis="saved assessment findings",
            ),
        ),
        evidence=(
            EvidenceItem(
                evidence_id="finding:one",
                source_type="finding",
                source_ref="assessment:assessment-1:finding:one",
                observed_at=BASE,
                facts={"status": "attention", "severity": "medium"},
            ),
        ),
        provenance={"assessment_id": "assessment-1"},
        generated_at=BASE,
    )


def _result_payload(bundle: AIReviewBundle) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "exchange_type": "veridra_ai_review_result",
        "review_id": "review-example-001",
        "source_bundle_id": bundle.bundle_id,
        "source_bundle_hash_sha256": bundle.bundle_hash_sha256,
        "generated_at": (BASE + timedelta(minutes=5)).isoformat(),
        "model_provenance": "GPT test fixture",
        "tool_provenance": "manual structured-file exchange",
        "interpretation": (
            "The saved evidence supports a bounded improvement opportunity."
        ),
        "strengths": ["Evidence is directly traceable."],
        "weaknesses_gaps": ["One medium-severity finding needs review."],
        "opportunity_assessment": (
            "Prioritise the observed issue without inventing business impact."
        ),
        "confidence": "high",
        "uncertainty": ["No traffic or conversion evidence is available."],
        "recommended_next_action": "Review the finding with a human operator.",
        "suggested_messaging_positioning": [
            "Lead with the observed issue, not estimated impact."
        ],
        "evidence_refs": ["finding:one"],
        "safe_actions": [
            {
                "action": "request_human_review",
                "reason": (
                    "A human should decide whether remediation is commercially relevant."
                ),
                "evidence_refs": ["finding:one"],
            }
        ],
    }
    payload["result_hash_sha256"] = result_integrity_hash(payload)
    return payload


def test_bundle_is_single_self_contained_hash_bound_contract() -> None:
    bundle = _bundle()

    assert bundle.schema_version == "1.0"
    assert bundle.exchange_type == "veridra_ai_review_bundle"
    assert len(bundle.bundle_id) == 24
    assert len(bundle.bundle_hash_sha256) == 64
    assert bundle.evidence[0].evidence_id == "finding:one"
    assert bundle.deterministic_scores[0].basis == "saved assessment findings"


def test_result_accepts_exact_bundle_and_known_evidence() -> None:
    bundle = _bundle()
    payload = _result_payload(bundle)

    result = parse_and_validate_result(json.dumps(payload), source_bundle=bundle)

    assert result.review_id == "review-example-001"
    assert result.source_bundle_id == bundle.bundle_id
    assert result.safe_actions[0].action.value == "request_human_review"


def test_result_rejects_tampered_content() -> None:
    bundle = _bundle()
    payload = _result_payload(bundle)
    payload["interpretation"] = "Tampered after the integrity digest was produced."

    with pytest.raises(AIReviewExchangeError, match="integrity"):
        parse_and_validate_result(json.dumps(payload), source_bundle=bundle)


def test_result_rejects_wrong_or_stale_bundle_binding() -> None:
    bundle = _bundle()
    payload = _result_payload(bundle)
    payload["source_bundle_id"] = "0" * 24
    payload["result_hash_sha256"] = result_integrity_hash(payload)

    with pytest.raises(AIReviewExchangeError, match="different"):
        parse_and_validate_result(json.dumps(payload), source_bundle=bundle)

    payload = _result_payload(bundle)
    payload["generated_at"] = (BASE - timedelta(minutes=1)).isoformat()
    payload["result_hash_sha256"] = result_integrity_hash(payload)
    with pytest.raises(AIReviewExchangeError, match="stale"):
        parse_and_validate_result(json.dumps(payload), source_bundle=bundle)


def test_result_rejects_unknown_evidence_reference() -> None:
    bundle = _bundle()
    payload = _result_payload(bundle)
    payload["evidence_refs"] = ["finding:missing"]
    payload["result_hash_sha256"] = result_integrity_hash(payload)

    with pytest.raises(AIReviewExchangeError, match="not present"):
        parse_and_validate_result(json.dumps(payload), source_bundle=bundle)
