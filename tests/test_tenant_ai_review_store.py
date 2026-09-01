from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from veridra.ai_review_exchange import (
    AIReviewBundle,
    AIReviewResult,
    EvidenceItem,
    ReviewContextType,
    build_review_bundle,
    result_integrity_hash,
)
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.tenant_ai_review_store import TenantAIReviewStore, TenantAIReviewStoreError

BASE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _identity(tenant: str) -> RequestIdentity:
    return RequestIdentity(
        user_id="1" * 24,
        tenant_id=tenant,
        membership_role=TenantRole.owner,
        session_id="s" * 24,
        authenticated_at=BASE,
    )


def _bundle() -> AIReviewBundle:
    return build_review_bundle(
        context_type=ReviewContextType.project,
        context_id="project-1",
        context_label="Project One",
        target="https://example.com/",
        context={"name": "Project One"},
        evidence=(
            EvidenceItem(
                evidence_id="finding:one",
                source_type="finding",
                source_ref="assessment:a:finding:one",
                facts={"severity": "medium"},
            ),
        ),
        generated_at=BASE,
    )


def _result(bundle: AIReviewBundle) -> AIReviewResult:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "exchange_type": "veridra_ai_review_result",
        "review_id": "review-project-1",
        "source_bundle_id": bundle.bundle_id,
        "source_bundle_hash_sha256": bundle.bundle_hash_sha256,
        "generated_at": (BASE + timedelta(minutes=1)).isoformat(),
        "model_provenance": "test-model",
        "tool_provenance": "test",
        "interpretation": "Bounded interpretation.",
        "strengths": [],
        "weaknesses_gaps": [],
        "opportunity_assessment": "Human review opportunity.",
        "confidence": "medium",
        "uncertainty": [],
        "recommended_next_action": "Review manually.",
        "suggested_messaging_positioning": [],
        "evidence_refs": ["finding:one"],
        "safe_actions": [],
    }
    payload["result_hash_sha256"] = result_integrity_hash(payload)
    return AIReviewResult.model_validate(payload)


def test_store_preserves_bundle_and_append_only_review_history(tmp_path: Path) -> None:
    store = TenantAIReviewStore(tmp_path)
    identity = _identity("a" * 24)
    bundle = _bundle()
    result = _result(bundle)

    store.save_bundle(identity, bundle)
    store.save_result(identity, bundle=bundle, result=result)

    assert store.load_bundle(
        identity,
        ReviewContextType.project,
        "project-1",
        bundle.bundle_id,
    ) == bundle
    assert store.load_result(
        identity,
        ReviewContextType.project,
        "project-1",
        result.review_id,
    ) == result
    history = store.list_results(identity, ReviewContextType.project, "project-1")
    assert [item.review_id for item in history] == ["review-project-1"]
    assert history[0].source_bundle_id == bundle.bundle_id
    assert history[0].model_provenance == "test-model"


def test_store_never_allows_same_review_id_to_change_content(tmp_path: Path) -> None:
    store = TenantAIReviewStore(tmp_path)
    identity = _identity("a" * 24)
    bundle = _bundle()
    result = _result(bundle)
    store.save_bundle(identity, bundle)
    store.save_result(identity, bundle=bundle, result=result)

    changed = result.model_copy(update={"interpretation": "Changed reasoning."})
    with pytest.raises(TenantAIReviewStoreError, match="already exists"):
        store.save_result(identity, bundle=bundle, result=changed)


def test_tenant_storage_isolated_by_identity(tmp_path: Path) -> None:
    store = TenantAIReviewStore(tmp_path)
    first = _identity("a" * 24)
    second = _identity("b" * 24)
    bundle = _bundle()
    store.save_bundle(first, bundle)

    with pytest.raises(TenantAIReviewStoreError, match="not found"):
        store.load_bundle(
            second,
            ReviewContextType.project,
            "project-1",
            bundle.bundle_id,
        )

    assert store.list_results(second, ReviewContextType.project, "project-1") == []
