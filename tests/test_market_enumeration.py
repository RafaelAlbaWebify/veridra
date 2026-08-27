from __future__ import annotations

from datetime import UTC, datetime

from veridra.assisted_discovery import (
    TraversalObservation,
    TraversalProgress,
    TraversalResult,
    TraversalStopReason,
)
from veridra.market_enumeration import aggregate_market, dublin_dentist_queries
from veridra.prospect_discovery import ObservedBusiness


def _business(*, key: str, name: str, website: str | None = None) -> ObservedBusiness:
    return ObservedBusiness.model_validate(
        {
            "provider": "assisted-google-maps",
            "provider_key": key,
            "name": name,
            "category": "Dentist",
            "locality": "Dublin",
            "administrative_area": "Dublin",
            "country_code": "IE",
            "website": website,
            "source_url": f"https://www.google.com/maps/place/{name.replace(' ', '+')}",
            "rating": 4.7,
            "review_count": 42,
            "profile_photo_signal_count": 2,
            "observed_at": datetime.now(UTC),
        }
    )


def _result(sequence: int, query: str, businesses: list[ObservedBusiness]) -> TraversalResult:
    observations = tuple(
        TraversalObservation(
            business=business,
            query_text=query,
            query_sequence=sequence,
            result_rank=index,
            first_seen_scroll_step=0,
        )
        for index, business in enumerate(businesses, start=1)
    )
    return TraversalResult(
        observations=observations,
        progress=TraversalProgress(
            query_text=query,
            query_sequence=sequence,
            scroll_step=3,
            unique_results=len(observations),
            stagnant_scrolls=0,
            elapsed_seconds=5.0,
            stop_reason=TraversalStopReason.end_of_list,
        ),
    )


def test_market_aggregation_deduplicates_across_queries_and_keeps_provenance() -> None:
    shared = _business(key="place-1", name="Shared Dental", website=None)
    first_only = _business(key="place-2", name="First Dental", website="https://first.ie")
    second_only = _business(key="place-3", name="Second Dental", website=None)

    market = aggregate_market(
        [
            _result(1, "dentist in Dublin 1, IE", [shared, first_only]),
            _result(2, "dentist in Dublin 2, IE", [shared, second_only]),
        ]
    )

    assert market.raw_observation_count == 4
    assert len(market.businesses) == 3
    assert market.coverage[0].new_unique == 2
    assert market.coverage[1].new_unique == 1
    assert market.coverage[1].duplicate_observations == 1

    shared_market = next(
        item for item in market.businesses if item.business.name == "Shared Dental"
    )
    assert shared_market.first_query_sequence == 1
    assert shared_market.observation_count == 2
    assert shared_market.seen_in_queries == (
        "dentist in Dublin 1, IE",
        "dentist in Dublin 2, IE",
    )
    assert shared_market.business.website is None


def test_dublin_plan_runs_city_and_all_district_queries() -> None:
    queries = dublin_dentist_queries()

    assert "dentist in Dublin, IE" in queries
    assert "dentist in Dublin 1, IE" in queries
    assert "dentist in Dublin 24, IE" in queries
    assert "dentist in Dublin 6W, IE" in queries
    assert "dental clinic in Dublin, IE" in queries
    assert len(queries) == len(set(queries))
