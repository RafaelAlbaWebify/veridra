from __future__ import annotations

from datetime import UTC, datetime

import pytest

from veridra.assisted_discovery import (
    AssistedDiscoveryConflict,
    AssistedDiscoveryManager,
    AssistedDiscoveryState,
    AssistedDiscoveryTransitionError,
    BoundedDiscoveryLimits,
    OrderedObservationAccumulator,
    TraversalProgress,
    TraversalResult,
    TraversalStopReason,
)
from veridra.prospect_discovery import ObservedBusiness

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def _business(provider_key: str = "place-1") -> ObservedBusiness:
    return ObservedBusiness.model_validate(
        {
            "provider": "assisted-google-maps",
            "provider_key": provider_key,
            "name": f"Business {provider_key}",
            "category": "Dental clinic",
            "locality": "Vigo",
            "administrative_area": "Pontevedra",
            "country_code": "ES",
            "website": f"https://{provider_key}.example",
            "source_url": f"https://maps.example/{provider_key}",
            "observed_at": NOW,
        }
    )


class FakeProvider:
    def __init__(self) -> None:
        self.launched_url = ""
        self.stopped = False
        self.fail_collect = False
        self.result = TraversalResult(
            observations=(
                OrderedObservationAccumulator(
                    query_text="dentist in Vigo, ES",
                    query_sequence=1,
                    limits=BoundedDiscoveryLimits(max_results=10),
                ).result(
                    scroll_step=0,
                    elapsed_seconds=0.1,
                    stop_reason=TraversalStopReason.end_of_list,
                ).observations
            ),
            progress=TraversalProgress(
                query_text="dentist in Vigo, ES",
                query_sequence=1,
                scroll_step=0,
                unique_results=0,
                stagnant_scrolls=0,
                elapsed_seconds=0.1,
                stop_reason=TraversalStopReason.end_of_list,
            ),
        )

    def launch(self, *, start_url: str) -> None:
        self.launched_url = start_url

    def collect_bounded(
        self,
        *,
        query_text: str,
        query_sequence: int,
        limits: BoundedDiscoveryLimits,
    ) -> TraversalResult:
        if self.fail_collect:
            raise RuntimeError("provider failed")
        accumulator = OrderedObservationAccumulator(
            query_text=query_text,
            query_sequence=query_sequence,
            limits=limits,
        )
        accumulator.add_batch([_business("place-1"), _business("place-2")], scroll_step=0)
        return accumulator.result(
            scroll_step=0,
            elapsed_seconds=0.2,
            stop_reason=TraversalStopReason.end_of_list,
        )

    def stop(self) -> None:
        self.stopped = True


def test_bounds_reject_unrestricted_values() -> None:
    with pytest.raises(ValueError, match="between 1 and 200"):
        BoundedDiscoveryLimits(max_results=500)
    with pytest.raises(ValueError, match="between 0 and 100"):
        BoundedDiscoveryLimits(max_scrolls=101)
    with pytest.raises(ValueError, match="between 0 and 300"):
        BoundedDiscoveryLimits(max_elapsed_seconds=301)


def test_accumulator_deduplicates_provider_identity_and_preserves_rank() -> None:
    limits = BoundedDiscoveryLimits(max_results=3, max_stagnant_scrolls=2)
    accumulator = OrderedObservationAccumulator(
        query_text="dentist in Vigo, ES",
        query_sequence=2,
        limits=limits,
    )

    added = accumulator.add_batch(
        [_business("A"), _business("a"), _business("B")],
        scroll_step=0,
    )

    assert added == 2
    assert [item.business.provider_key for item in accumulator.observations] == ["A", "B"]
    assert [item.result_rank for item in accumulator.observations] == [1, 2]
    assert all(item.query_sequence == 2 for item in accumulator.observations)


def test_accumulator_stops_on_server_owned_result_limit() -> None:
    limits = BoundedDiscoveryLimits(max_results=2)
    accumulator = OrderedObservationAccumulator(
        query_text="dentist in Vigo, ES",
        query_sequence=1,
        limits=limits,
    )
    accumulator.add_batch(
        [_business("1"), _business("2"), _business("3")],
        scroll_step=0,
    )

    assert len(accumulator.observations) == 2
    assert (
        accumulator.evaluate_stop(scroll_step=0, elapsed_seconds=1.0)
        is TraversalStopReason.max_results
    )


def test_accumulator_stops_after_stagnation() -> None:
    limits = BoundedDiscoveryLimits(max_stagnant_scrolls=2)
    accumulator = OrderedObservationAccumulator(
        query_text="dentist in Vigo, ES",
        query_sequence=1,
        limits=limits,
    )
    accumulator.add_batch([_business()], scroll_step=0)
    accumulator.add_batch([_business()], scroll_step=1)
    accumulator.add_batch([_business()], scroll_step=2)

    assert accumulator.stagnant_scrolls == 2
    assert (
        accumulator.evaluate_stop(scroll_step=2, elapsed_seconds=1.0)
        is TraversalStopReason.no_new_results
    )


def test_operator_must_mark_browser_ready_before_collection() -> None:
    provider = FakeProvider()
    manager = AssistedDiscoveryManager(provider)
    session = manager.launch(
        query_text="dentist in Vigo, ES",
        query_sequence=1,
        start_url="https://maps.example/search",
    )

    assert session.state is AssistedDiscoveryState.awaiting_operator
    assert provider.launched_url == "https://maps.example/search"
    with pytest.raises(AssistedDiscoveryTransitionError, match="marks the browser ready"):
        manager.collect(session.session_id or "", limits=BoundedDiscoveryLimits())


def test_complete_assisted_lifecycle_reaches_review_then_stop() -> None:
    provider = FakeProvider()
    manager = AssistedDiscoveryManager(provider)
    launched = manager.launch(
        query_text="dentist in Vigo, ES",
        query_sequence=1,
        start_url="https://maps.example/search",
    )
    ready = manager.mark_ready(launched.session_id or "")
    reviewed = manager.collect(
        ready.session_id or "",
        limits=BoundedDiscoveryLimits(max_results=10),
    )

    assert reviewed.state is AssistedDiscoveryState.review
    assert reviewed.progress is not None
    assert reviewed.progress.stop_reason is TraversalStopReason.end_of_list
    assert [item.provider_key for item in manager.included_businesses(reviewed.session_id or "")] == [
        "place-1",
        "place-2",
    ]

    stopped = manager.stop(reviewed.session_id)
    assert stopped.state is AssistedDiscoveryState.stopped
    assert provider.stopped is True


def test_second_active_session_is_rejected() -> None:
    manager = AssistedDiscoveryManager(FakeProvider())
    manager.launch(
        query_text="dentist in Vigo, ES",
        query_sequence=1,
        start_url="https://maps.example/search",
    )

    with pytest.raises(AssistedDiscoveryConflict):
        manager.launch(
            query_text="plumber in Vigo, ES",
            query_sequence=2,
            start_url="https://maps.example/search2",
        )


def test_provider_failure_returns_session_to_ready_without_fake_results() -> None:
    provider = FakeProvider()
    provider.fail_collect = True
    manager = AssistedDiscoveryManager(provider)
    launched = manager.launch(
        query_text="dentist in Vigo, ES",
        query_sequence=1,
        start_url="https://maps.example/search",
    )
    manager.mark_ready(launched.session_id or "")

    with pytest.raises(RuntimeError, match="provider failed"):
        manager.collect(
            launched.session_id or "",
            limits=BoundedDiscoveryLimits(),
        )

    snapshot = manager.snapshot()
    assert snapshot.state is AssistedDiscoveryState.ready
    assert snapshot.observations == ()
    assert snapshot.error == "provider failed"
    assert snapshot.progress is not None
    assert snapshot.progress.stop_reason is TraversalStopReason.provider_error
