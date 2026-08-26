from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from . import review_intelligence_hardened_cli as hardened
from .review_intelligence_cli import _text


def _strategy_rows(
    reviews: list[dict[str, object]], strategy: str
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for review in reviews:
        strategies = review.get("sample_strategies")
        if isinstance(strategies, list) and strategy in strategies:
            rows.append(review)
            continue
        if _text(review.get("sample_strategy")) == strategy:
            rows.append(review)
    return rows


def _parsed_dates(rows: list[dict[str, object]]) -> list[datetime]:
    values: list[datetime] = []
    for row in rows:
        raw = _text(row.get("approximate_review_date"))
        if not raw:
            continue
        try:
            values.append(datetime.fromisoformat(raw).replace(tzinfo=UTC))
        except ValueError:
            continue
    return values


def _response_rate(rows: list[dict[str, object]]) -> float | None:
    if not rows:
        return None
    responses = sum(1 for row in rows if row.get("owner_response_present") is True)
    return round(responses / len(rows), 3)


def strategy_safe_statistics(
    reviews: list[dict[str, object]], *, now: datetime
) -> dict[str, object]:
    newest = _strategy_rows(reviews, "newest")
    lowest = _strategy_rows(reviews, "lowest")
    highest = _strategy_rows(reviews, "highest")
    newest_dates = _parsed_dates(newest)

    def recent_count(days: int) -> int:
        cutoff = now - hardened.timedelta(days=days)
        return sum(1 for value in newest_dates if value >= cutoff)

    negative_lowest = [
        row
        for row in lowest
        if isinstance(row.get("rating"), int) and cast(int, row["rating"]) <= 3
    ]

    oldest_newest = min(newest_dates).date().isoformat() if newest_dates else None
    newest_limit_reached = len(newest) >= hardened._DEFAULT_PER_STRATEGY

    return {
        "merged_evidence_items": len(reviews),
        "newest_sample": {
            "sample_size": len(newest),
            "dated_sample_size": len(newest_dates),
            "sampled_reviews_within_30_days": recent_count(30),
            "sampled_reviews_within_90_days": recent_count(90),
            "sampled_reviews_within_365_days": recent_count(365),
            "oldest_sampled_review_date": oldest_newest,
            "owner_response_rate_sample": _response_rate(newest),
            "scope_note": (
                "These values describe only the reviews captured after explicitly selecting Newest. "
                "Recent counts are sample counts, not total review-history counts. If the strategy "
                "limit was reached, they are lower bounds for the corresponding period whenever all "
                "sampled reviews fall inside that period."
            ),
        },
        "lowest_sample": {
            "sample_size": len(lowest),
            "negative_review_count_sample": len(negative_lowest),
            "negative_review_response_rate_sample": _response_rate(negative_lowest),
            "scope_note": (
                "Negative-response behavior is measured only inside the explicitly selected Lowest "
                "rating sample and must not be presented as an overall business response rate."
            ),
        },
        "highest_sample": {
            "sample_size": len(highest),
            "scope_note": (
                "Highest-rating reviews are preserved for positive-theme analysis; no population-level "
                "rating distribution is inferred from this intentionally biased sample."
            ),
        },
        "strategy_limit_reached": {
            "newest": newest_limit_reached,
            "lowest": len(lowest) >= hardened._DEFAULT_PER_STRATEGY,
            "highest": len(highest) >= hardened._DEFAULT_PER_STRATEGY,
        },
        "population_metrics_suppressed": [
            "review_velocity",
            "overall_owner_response_rate",
            "overall_rating_distribution",
        ],
        "scope_note": (
            "VERIDRA uses a deliberately stratified newest/lowest/highest evidence sample. Merged "
            "review rows are suitable for evidence inspection and AI theme analysis, but are not a "
            "random or complete sample of the business's review population."
        ),
    }


def run(argv: Sequence[str] | None = None) -> int:
    hardened._statistics = strategy_safe_statistics
    return hardened.run(argv)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
