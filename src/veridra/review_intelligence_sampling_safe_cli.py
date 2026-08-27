from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

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
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        values.append(parsed.astimezone(UTC))
    return values


def _response_rate(rows: list[dict[str, object]]) -> float | None:
    if not rows:
        return None
    responses = sum(1 for row in rows if row.get("owner_response_present") is True)
    return round(responses / len(rows), 3)


def _negative_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        rating = row.get("rating")
        if isinstance(rating, int) and rating <= 3:
            output.append(row)
    return output


def strategy_safe_statistics(
    reviews: list[dict[str, object]], *, now: datetime
) -> dict[str, object]:
    newest = _strategy_rows(reviews, "newest")
    lowest = _strategy_rows(reviews, "lowest")
    highest = _strategy_rows(reviews, "highest")
    newest_dates = _parsed_dates(newest)
    negative_lowest = _negative_rows(lowest)

    def recent_count(days: int) -> int | None:
        if not newest:
            return None
        cutoff = now.astimezone(UTC) - timedelta(days=days)
        return sum(1 for value in newest_dates if value >= cutoff)

    return {
        "merged_evidence_items": len(reviews),
        "newest_sample": {
            "available": bool(newest),
            "sample_size": len(newest),
            "dated_sample_size": len(newest_dates),
            "sampled_reviews_within_30_days": recent_count(30),
            "sampled_reviews_within_90_days": recent_count(90),
            "sampled_reviews_within_365_days": recent_count(365),
            "oldest_sampled_review_date": (
                min(newest_dates).date().isoformat() if newest_dates else None
            ),
            "owner_response_rate_sample": _response_rate(newest),
            "scope_note": (
                "These values describe only reviews captured after explicitly selecting Newest. "
                "Recent counts are bounded sample counts, not totals for the business's complete "
                "review history. Review velocity is intentionally not inferred from this sample."
            ),
        },
        "lowest_sample": {
            "available": bool(lowest),
            "sample_size": len(lowest),
            "negative_review_count_sample": len(negative_lowest),
            "negative_review_response_rate_sample": _response_rate(negative_lowest),
            "scope_note": (
                "Negative-review response behavior is measured only inside the explicitly selected "
                "Lowest rating sample and must not be presented as an overall response rate."
            ),
        },
        "highest_sample": {
            "available": bool(highest),
            "sample_size": len(highest),
            "scope_note": (
                "Highest-rating reviews are retained for positive-theme evidence. "
                "No population-level rating distribution is inferred from this intentionally "
                "biased sample."
            ),
        },
        "population_metrics_suppressed": [
            "review_velocity",
            "overall_owner_response_rate",
            "overall_rating_distribution",
        ],
        "scope_note": (
            "VERIDRA deliberately combines newest, lowest-rating and highest-rating review "
            "evidence. The merged rows are useful for inspection and AI theme analysis but are "
            "not a random or complete sample of the business's review population. Every statistic "
            "is therefore scoped to the sampling strategy that supports it."
        ),
    }


def run(argv: Sequence[str] | None = None) -> int:
    hardened._statistics = strategy_safe_statistics
    return hardened.run(argv)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
