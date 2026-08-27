from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MarketOpportunityBand(StrEnum):
    priority = "priority"
    high = "high"
    medium = "medium"
    low = "low"


@dataclass(frozen=True, slots=True)
class MarketBenchmarks:
    review_q1: int
    review_median: int
    review_q3: int


@dataclass(frozen=True, slots=True)
class MarketOpportunityAssessment:
    score: int
    band: MarketOpportunityBand
    digital_gap_score: int
    activity_score: int
    reasons: tuple[str, ...]


def _quantile(sorted_values: list[int], fraction: float) -> int:
    if not sorted_values:
        return 0
    index = round((len(sorted_values) - 1) * fraction)
    return sorted_values[index]


def review_benchmarks(review_counts: list[int]) -> MarketBenchmarks:
    values = sorted(value for value in review_counts if value >= 0)
    return MarketBenchmarks(
        review_q1=_quantile(values, 0.25),
        review_median=_quantile(values, 0.50),
        review_q3=_quantile(values, 0.75),
    )


def _activity_score(review_count: int | None, benchmarks: MarketBenchmarks) -> tuple[int, str]:
    if review_count is None:
        return 0, "Google review activity was not available for comparison."
    if review_count >= benchmarks.review_q3 and review_count > 0:
        return 30, "Customer activity is in the top quartile of the observed market."
    if review_count >= benchmarks.review_median and review_count > 0:
        return 24, "Customer activity is at or above the observed market median."
    if review_count >= benchmarks.review_q1 and review_count > 0:
        return 16, "Customer activity is at or above the observed market lower quartile."
    if review_count > 0:
        return 8, "Some customer activity is visible, but it is below the market lower quartile."
    return 0, "No Google review activity was observed."


def assess_market_opportunity(
    *,
    website_url: str | None,
    booking_links: tuple[str, ...],
    rating: float | None,
    review_count: int | None,
    benchmarks: MarketBenchmarks,
) -> MarketOpportunityAssessment:
    """Score post-enrichment opportunity without treating weak reputation as a Webify problem."""

    reasons: list[str] = []
    gap = 0

    if not website_url:
        gap += 55
        reasons.append("No official website was observed after GBP detail-page enrichment.")

    if not booking_links:
        gap += 10
        reasons.append(
            "No external booking or appointment action was observed on the public Google profile."
        )
    else:
        reasons.append("A public Google booking or appointment action was observed.")

    activity, activity_reason = _activity_score(review_count, benchmarks)
    reasons.append(activity_reason)

    if rating is not None and review_count and review_count >= 10:
        if rating >= 4.5:
            reasons.append(
                "Strong rating supports the possibility of a healthy real-world business behind "
                "the digital gap."
            )
        elif rating < 4.2:
            reasons.append(
                "Lower rating is treated as reputation context only and does not add opportunity "
                "points."
            )

    score = min(100, gap + activity)
    if not website_url and activity >= 16:
        band = MarketOpportunityBand.priority
    elif score >= 55 and activity >= 8:
        band = MarketOpportunityBand.high
    elif score >= 30:
        band = MarketOpportunityBand.medium
    else:
        band = MarketOpportunityBand.low

    return MarketOpportunityAssessment(
        score=score,
        band=band,
        digital_gap_score=gap,
        activity_score=activity,
        reasons=tuple(reasons),
    )
