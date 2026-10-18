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
        _review(
            "visible",
            strategy="visible-default",
            rating=5,
            date="2026-08-20",
            responded=False,
        ),
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


def test_sampling_policy_does_not_modify_hardened_functions(monkeypatch) -> None:
    from veridra import review_intelligence_hardened_cli as hardened
    from veridra import review_intelligence_sampling_safe_cli as sampling

    originals = (
        hardened._statistics,
        hardened._review_from_card,
        hardened._click_reviews,
        hardened._choose_sort,
        hardened._collect_strategy,
    )
    captured: list[object] = []

    def fake_run(argv: object, *, policy: object | None = None) -> int:
        captured.append(policy)
        return 0

    monkeypatch.setattr(hardened, "run", fake_run)
    assert sampling.run(["--help"]) == 0
    assert len(captured) == 1
    policy = captured[0]
    assert isinstance(policy, hardened.ReviewCollectionPolicy)
    assert policy.statistics is sampling.strategy_safe_statistics
    assert policy.review_from_card is sampling.review_with_provenance
    assert policy.click_reviews is sampling.retry_click_reviews
    assert policy.choose_sort is sampling.retry_choose_sort
    assert policy.collect_strategy is sampling.collect_strategy_with_provenance
    assert originals == (
        hardened._statistics,
        hardened._review_from_card,
        hardened._click_reviews,
        hardened._choose_sort,
        hardened._collect_strategy,
    )


def test_provenance_collector_uses_retry_and_provenance_callbacks(monkeypatch) -> None:
    from veridra import review_intelligence_sampling_safe_cli as sampling

    seen: dict[str, object] = {}

    def fake_collect(
        page: object, **kwargs: object
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        seen.update(kwargs)
        return ([{"evidence_id": "one"}], {"strategy": "newest"})

    class Page:
        url = "https://www.google.com/maps/place/example"

    monkeypatch.setattr(sampling, "_BASE_COLLECT_STRATEGY", fake_collect)
    rows, diagnostics = sampling.collect_strategy_with_provenance(
        Page(), business_name="Example", strategy="newest", limit=1
    )
    assert seen["choose_sort"] is sampling.retry_choose_sort
    assert seen["review_from_card"] is sampling.review_with_provenance
    assert rows[0]["source_url"] == Page.url
    assert diagnostics["source_url"] == Page.url
