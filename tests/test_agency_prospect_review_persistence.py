from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.agency_prospect_discovery_web import (
    _DiscoveryReviewBatch,
    _delete_review,
    _load_review,
    _review_store_path,
    _save_review,
)
from veridra.assisted_discovery import BoundedDiscoveryLimits, TraversalObservation
from veridra.prospect_discovery import ObservedBusiness


def _batch() -> _DiscoveryReviewBatch:
    observation = TraversalObservation(
        business=ObservedBusiness.model_validate(
            {
                "provider": "assisted-google-maps",
                "provider_key": "google-maps:test",
                "name": "Example Solicitors",
                "category": "Solicitor",
                "locality": "Dublin",
                "administrative_area": "Dublin",
                "country_code": "IE",
                "website": "https://example.test/",
                "source_url": "https://www.google.com/maps/place/example",
                "rating": 4.8,
                "review_count": 120,
                "profile_photo_signal_count": 3,
                "observed_at": datetime(2026, 10, 5, 6, 0, tzinfo=UTC),
            }
        ),
        query_text="solicitors in Dublin, Ireland",
        query_sequence=1,
        result_rank=1,
        first_seen_scroll_step=0,
    )
    return _DiscoveryReviewBatch(
        tenant_id="tenant-one",
        session_id="session-one",
        manager=None,
        limits=BoundedDiscoveryLimits(
            max_results=20,
            max_scrolls=10,
            max_elapsed_seconds=45,
            max_stagnant_scrolls=3,
        ),
        observations=(observation,),
    )


def test_completed_review_round_trips_through_durable_storage(tmp_path: Path) -> None:
    original = _batch()

    _save_review(tmp_path, original)
    restored = _load_review(
        tmp_path,
        tenant_id=original.tenant_id,
        session_id=original.session_id,
    )

    assert restored is not None
    assert restored.manager is None
    assert restored.tenant_id == original.tenant_id
    assert restored.session_id == original.session_id
    assert restored.limits == original.limits
    assert restored.observations == original.observations


def test_review_storage_is_tenant_scoped_and_deleted_after_completion(tmp_path: Path) -> None:
    batch = _batch()
    _save_review(tmp_path, batch)

    path = _review_store_path(
        tmp_path,
        tenant_id=batch.tenant_id,
        session_id=batch.session_id,
    )
    assert path is not None and path.exists()
    assert _load_review(
        tmp_path,
        tenant_id="different-tenant",
        session_id=batch.session_id,
    ) is None

    _delete_review(
        tmp_path,
        tenant_id=batch.tenant_id,
        session_id=batch.session_id,
    )
    assert not path.exists()
