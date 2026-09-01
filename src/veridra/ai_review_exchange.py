from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EXPORT_SCHEMA_VERSION = "1.0"
RESULT_SCHEMA_VERSION = "1.0"


class AIReviewExchangeError(ValueError):
    pass


class ReviewContextType(StrEnum):
    prospect = "prospect"
    customer = "customer"
    project = "project"


class ReviewConfidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class SafeActionType(StrEnum):
    flag_for_follow_up = "flag_for_follow_up"
    request_human_review = "request_human_review"
    create_remediation_review = "create_remediation_review"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    evidence_id: str = Field(min_length=1, max_length=240)
    source_type: str = Field(min_length=1, max_length=80)
    source_ref: str = Field(min_length=1, max_length=500)
    observed_at: datetime | None = None
    facts: dict[str, Any] = Field(default_factory=dict)


class DeterministicScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    key: str = Field(min_length=1, max_length=120)
    value: int | float | str | bool
    basis: str = Field(min_length=1, max_length=500)


class AIReviewBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = EXPORT_SCHEMA_VERSION
    exchange_type: Literal["veridra_ai_review_bundle"] = "veridra_ai_review_bundle"
    bundle_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    bundle_hash_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime
    context_type: ReviewContextType
    context_id: str = Field(min_length=1, max_length=160)
    context_label: str = Field(min_length=1, max_length=240)
    target: str | None = Field(default=None, max_length=2048)
    context: dict[str, Any] = Field(default_factory=dict)
    deterministic_scores: tuple[DeterministicScore, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    provenance: dict[str, Any] = Field(default_factory=dict)
    instructions: tuple[str, ...] = (
        "Treat VERIDRA evidence and deterministic scores as authoritative inputs.",
        (
            "Do not invent missing facts, traffic, rankings, audience data, "
            "business outcomes or outreach events."
        ),
        (
            "Return a schema-valid veridra_ai_review_result bound to this exact "
            "bundle id and SHA-256 hash."
        ),
    )


class SafeAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    action: SafeActionType
    reason: str = Field(min_length=1, max_length=1000)
    evidence_refs: tuple[str, ...] = ()


class AIReviewResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = RESULT_SCHEMA_VERSION
    exchange_type: Literal["veridra_ai_review_result"] = "veridra_ai_review_result"
    review_id: str = Field(min_length=8, max_length=160)
    source_bundle_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    source_bundle_hash_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime
    model_provenance: str | None = Field(default=None, max_length=240)
    tool_provenance: str | None = Field(default=None, max_length=500)
    interpretation: str = Field(min_length=1, max_length=8000)
    strengths: tuple[str, ...] = ()
    weaknesses_gaps: tuple[str, ...] = ()
    opportunity_assessment: str = Field(min_length=1, max_length=5000)
    confidence: ReviewConfidence = ReviewConfidence.unknown
    uncertainty: tuple[str, ...] = ()
    recommended_next_action: str = Field(min_length=1, max_length=2000)
    suggested_messaging_positioning: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    safe_actions: tuple[SafeAction, ...] = ()
    result_hash_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def referenced_evidence_is_not_empty_string(self) -> AIReviewResult:
        if any(not value.strip() for value in self.evidence_refs):
            raise ValueError("Evidence references must not be blank.")
        for action in self.safe_actions:
            if any(not value.strip() for value in action.evidence_refs):
                raise ValueError("Safe-action evidence references must not be blank.")
        return self


def _canonical_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _json_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.pop("result_hash_sha256", None)
    generated_at = normalized.get("generated_at")
    if isinstance(generated_at, datetime):
        normalized["generated_at"] = _json_datetime(generated_at)
    elif isinstance(generated_at, str):
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            normalized["generated_at"] = _json_datetime(parsed)
    return normalized


def build_review_bundle(
    *,
    context_type: ReviewContextType,
    context_id: str,
    context_label: str,
    target: str | None,
    context: dict[str, Any],
    deterministic_scores: tuple[DeterministicScore, ...] = (),
    evidence: tuple[EvidenceItem, ...] = (),
    provenance: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> AIReviewBundle:
    timestamp = (generated_at or datetime.now(UTC)).astimezone(UTC)
    base = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exchange_type": "veridra_ai_review_bundle",
        "generated_at": _json_datetime(timestamp),
        "context_type": context_type.value,
        "context_id": context_id,
        "context_label": context_label,
        "target": target,
        "context": context,
        "deterministic_scores": [
            item.model_dump(mode="json") for item in deterministic_scores
        ],
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "provenance": provenance or {},
        "instructions": list(AIReviewBundle.model_fields["instructions"].default),
    }
    bundle_id = _sha256(base)[:24]
    with_id = {**base, "bundle_id": bundle_id}
    bundle_hash = _sha256(with_id)
    return AIReviewBundle.model_validate(
        {**with_id, "bundle_hash_sha256": bundle_hash}
    )


def bundle_integrity_hash(bundle: AIReviewBundle) -> str:
    payload = bundle.model_dump(mode="json")
    payload.pop("bundle_hash_sha256", None)
    return _sha256(payload)


def result_integrity_hash(result: AIReviewResult | dict[str, Any]) -> str:
    payload = (
        result.model_dump(mode="json")
        if isinstance(result, AIReviewResult)
        else dict(result)
    )
    return _sha256(_canonical_result_payload(payload))


def parse_and_validate_result(
    raw: str | bytes,
    *,
    source_bundle: AIReviewBundle,
) -> AIReviewResult:
    if bundle_integrity_hash(source_bundle) != source_bundle.bundle_hash_sha256:
        raise AIReviewExchangeError(
            "Source AI review bundle failed integrity validation."
        )
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise AIReviewExchangeError("Reviewed result is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AIReviewExchangeError("Reviewed result must be a JSON object.")
    try:
        result = AIReviewResult.model_validate(payload)
    except ValueError as exc:
        raise AIReviewExchangeError(
            "Reviewed result does not match schema 1.0."
        ) from exc
    if result.source_bundle_id != source_bundle.bundle_id:
        raise AIReviewExchangeError(
            "Reviewed result belongs to a different AI review bundle."
        )
    if result.source_bundle_hash_sha256 != source_bundle.bundle_hash_sha256:
        raise AIReviewExchangeError(
            "Reviewed result source hash does not match the exported bundle."
        )
    if result.generated_at.astimezone(UTC) < source_bundle.generated_at.astimezone(UTC):
        raise AIReviewExchangeError(
            "Reviewed result predates its source bundle and is stale."
        )
    if result_integrity_hash(result) != result.result_hash_sha256:
        raise AIReviewExchangeError("Reviewed result failed integrity validation.")
    known_refs = {item.evidence_id for item in source_bundle.evidence}
    used_refs = set(result.evidence_refs)
    for action in result.safe_actions:
        used_refs.update(action.evidence_refs)
    unknown = sorted(used_refs - known_refs)
    if unknown:
        raise AIReviewExchangeError(
            "Reviewed result cites evidence that is not present in the source bundle: "
            + ", ".join(unknown)
        )
    return result


def result_template(bundle: AIReviewBundle) -> dict[str, Any]:
    """Return a fillable result shape; hash covers all fields except the hash field."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "exchange_type": "veridra_ai_review_result",
        "review_id": f"review-{bundle.bundle_id}",
        "source_bundle_id": bundle.bundle_id,
        "source_bundle_hash_sha256": bundle.bundle_hash_sha256,
        "generated_at": _json_datetime(datetime.now(UTC)),
        "model_provenance": None,
        "tool_provenance": None,
        "interpretation": "",
        "strengths": [],
        "weaknesses_gaps": [],
        "opportunity_assessment": "",
        "confidence": "unknown",
        "uncertainty": [],
        "recommended_next_action": "",
        "suggested_messaging_positioning": [],
        "evidence_refs": [],
        "safe_actions": [],
        "result_hash_sha256": (
            "REPLACE_WITH_SHA256_OF_CANONICAL_RESULT_WITHOUT_THIS_FIELD"
        ),
    }
