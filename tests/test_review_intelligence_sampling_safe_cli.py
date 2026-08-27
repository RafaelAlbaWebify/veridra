from __future__ import annotations

from datetime import UTC, datetime

from veridra.review_intelligence_sampling_safe_cli import strategy_safe_statistics


def _review(
    evidence_id: str,
    *,
    strategy: str,
    rating: int,
    date: str,
    responded: bool,
    extra_strategies: list[str] | None = None,
) -> dict[str, object]:
    strategies = [strategy]
    if extra_strategies:
        strategies.extend(extra_strategies)
    return {
        "evidence_id": evidence_id,
        "sample_strategy": strategy,
        "sample_strategies": strategies,
        "rating": rating,
        "approximate_review_date": date,
        "owner_response_present": responded,
    }


def test_statistics_keep_recency_scoped_to_newest_sample() -> None:
    reviews = [
        _review("new-1", strategy="newest", rating=5, date="2026-08-20", responded=True),
        _review("new-2", strategy="newest", rating=4, date="2026-07-20", responded=False),
        _review("low-old", strategy="lowest", rating=1, date="2024-01-01", responded=True),
        _review("high-old", strategy="highest", rating=5, date="2023-01-01", responded=False),
    ]

    stats = strategy_safe_statistics(
        reviews,
        now=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
    )

    newest = stats["newest_sample"]
    assert isinstance(newest, dict)
    assert newest["sample_size"] == 2
    assert newest["sampled_reviews_within_30_days"] == 1
    assert newest["sampled_reviews_within_90_days"] == 2
    assert newest["sampled_reviews_within_365_days"] == 2
    assert newest["owner_response_rate_sample"] == 0.5
    assert "sampled_review_velocity_per_month_365d" not in stats


def test_negative_response_rate_uses_only_lowest_negative_sample() -> None:
    reviews = [
        _review("low-1", strategy="lowest", rating=1, date="2026-01-01", responded=True),
        _review("low-2", strategy="lowest", rating=2, date="2026-01-02", responded=False),
        _review("low-5", strategy="lowest", rating=5, date="2026-01-03", responded=True),
        _review("new-1", strategy="newest", rating=1, date="2026-08-20", responded=False),
    ]

    stats = strategy_safe_statistics(
        reviews,
        now=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
    )

    lowest = stats["lowest_sample"]
    assert isinstance(lowest, dict)
    assert lowest["sample_size"] == 3
    assert lowest["negative_review_count_sample"] == 2
    assert lowest["negative_review_response_rate_sample"] == 0.5


def test_merged_stratified_sample_suppresses_population_metrics() -> None:
    reviews = [
        _review("new", strategy="newest", rating=4, date="2026-08-20", responded=True),
        _review("low", strategy="lowest", rating=1, date="2025-01-01", responded=False),
        _review("high", strategy="highest", rating=5, date="2024-01-01", responded=True),
    ]

    stats = strategy_safe_statistics(
        reviews,
        now=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
    )

    assert stats["merged_evidence_items"] == 3
    assert stats["population_metrics_suppressed"] == [
        "review_velocity",
        "overall_owner_response_rate",
        "overall_rating_distribution",
    ]
    assert "rating_distribution_sample" not in stats
    assert "owner_response_rate_sample" not in stats


def test_review_seen_in_multiple_strategies_contributes_to_each_strategy_scope() -> None:
    reviews = [
        _review(
            "shared",
            strategy="newest",
            rating=1,
            date="2026-08-20",
            responded=True,
            extra_strategies=["lowest"],
        )
    ]

    stats = strategy_safe_statistics(
        reviews,
        now=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
    )

    newest = stats["newest_sample"]
    lowest = stats["lowest_sample"]
    assert isinstance(newest, dict)
    assert isinstance(lowest, dict)
    assert newest["sample_size"] == 1
    assert lowest["sample_size"] == 1
    assert lowest["negative_review_response_rate_sample"] == 1.0


def test_recency_is_unavailable_when_newest_sort_was_not_captured() -> None:
    reviews = [
        _review("visible", strategy="visible-default", rating=5, date="2026-08-20", responded=False),
        _review("low", strategy="lowest", rating=1, date="2026-01-01", responded=False),
    ]

    stats = strategy_safe_statistics(
        reviews,
        now=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
    )

    newest = stats["newest_sample"]
    assert isinstance(newest, dict)
    assert newest["available"] is False
    assert newest["sample_size"] == 0
    assert newest["sampled_reviews_within_30_days"] is None
    assert newest["sampled_reviews_within_365_days"] is None
