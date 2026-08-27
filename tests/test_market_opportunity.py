from __future__ import annotations

from veridra.market_opportunity import (
    MarketOpportunityBand,
    assess_market_opportunity,
    review_benchmarks,
)


def test_review_benchmarks_are_market_relative() -> None:
    benchmarks = review_benchmarks([5, 10, 20, 40, 80])

    assert benchmarks.review_q1 == 10
    assert benchmarks.review_median == 20
    assert benchmarks.review_q3 == 40


def test_verified_no_website_with_healthy_activity_is_priority() -> None:
    benchmarks = review_benchmarks([10, 20, 40, 80])

    result = assess_market_opportunity(
        website_url=None,
        website_absence_verified=True,
        booking_links=(),
        rating=4.8,
        review_count=40,
        benchmarks=benchmarks,
    )

    assert result.band is MarketOpportunityBand.priority
    assert result.digital_gap_score == 65
    assert result.activity_score >= 16
    assert result.website_verification_required is False


def test_unverified_maps_website_absence_is_not_priority() -> None:
    benchmarks = review_benchmarks([10, 20, 40, 80])

    result = assess_market_opportunity(
        website_url=None,
        booking_links=(),
        rating=4.8,
        review_count=40,
        benchmarks=benchmarks,
    )

    assert result.band is MarketOpportunityBand.high
    assert result.digital_gap_score == 25
    assert result.website_verification_required is True


def test_no_website_without_activity_is_not_priority() -> None:
    benchmarks = review_benchmarks([10, 20, 40, 80])

    result = assess_market_opportunity(
        website_url=None,
        website_absence_verified=True,
        booking_links=(),
        rating=None,
        review_count=0,
        benchmarks=benchmarks,
    )

    assert result.band is MarketOpportunityBand.medium
    assert result.activity_score == 0


def test_low_reputation_blocks_priority_even_when_no_website_is_verified() -> None:
    benchmarks = review_benchmarks([10, 20, 40, 80])

    result = assess_market_opportunity(
        website_url=None,
        website_absence_verified=True,
        booking_links=(),
        rating=3.6,
        review_count=80,
        benchmarks=benchmarks,
    )

    assert result.band is MarketOpportunityBand.medium
    assert result.score == 95
    assert any("Priority is blocked" in reason for reason in result.reasons)


def test_mature_website_with_booking_stays_low_even_with_strong_activity() -> None:
    benchmarks = review_benchmarks([10, 20, 40, 80])

    result = assess_market_opportunity(
        website_url="https://clinic.example",
        booking_links=("https://booking.example/clinic",),
        rating=4.9,
        review_count=80,
        benchmarks=benchmarks,
    )

    assert result.digital_gap_score == 0
    assert result.activity_score == 30
    assert result.band is MarketOpportunityBand.medium


def test_missing_booking_action_is_only_a_modest_gap() -> None:
    benchmarks = review_benchmarks([10, 20, 40, 80])

    result = assess_market_opportunity(
        website_url="https://clinic.example",
        booking_links=(),
        rating=4.9,
        review_count=80,
        benchmarks=benchmarks,
    )

    assert result.digital_gap_score == 10
    assert result.score == 40
    assert result.band is MarketOpportunityBand.medium
