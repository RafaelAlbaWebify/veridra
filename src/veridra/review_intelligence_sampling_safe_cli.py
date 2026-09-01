from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from . import review_intelligence_hardened_cli as hardened
from .review_intelligence_cli import _text

_BASE_CLICK_REVIEWS = hardened._click_reviews
_BASE_CHOOSE_SORT = hardened._choose_sort
_BASE_COLLECT_STRATEGY = hardened._collect_strategy
_BASE_REVIEW_FROM_CARD = hardened._review_from_card
_MANUAL_INTERRUPTION_SELECTORS: tuple[tuple[str, str], ...] = (
    ("consent", "button:has-text('Accept all')"),
    ("consent", "button:has-text('Reject all')"),
    ("sign-in", "form[action*='signin']"),
    ("sign-in", "input[type='email']"),
    ("captcha", "iframe[src*='recaptcha']"),
    ("captcha", "form[action*='captcha']"),
)


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


def _first_text(card: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            node = card.locator(selector).first
            if not node.count():
                continue
            value = _text(node.inner_text(timeout=2000))
            if value:
                return value
        except Exception:
            continue
    return ""


def _first_attribute(card: Any, selectors: tuple[str, ...], attribute: str) -> str:
    for selector in selectors:
        try:
            node = card.locator(selector).first
            if not node.count():
                continue
            value = _text(node.get_attribute(attribute))
            if value:
                return value
        except Exception:
            continue
    return ""


def review_with_provenance(
    card: Any,
    *,
    business_name: str,
    strategy: str,
    observed_at: datetime,
) -> dict[str, object] | None:
    row = _BASE_REVIEW_FROM_CARD(
        card,
        business_name=business_name,
        strategy=strategy,
        observed_at=observed_at,
    )
    if row is None:
        return None

    owner_response_date_text = _first_text(
        card,
        (
            ".CDe7pd .rsqaWe",
            ".CDe7pd span.rsqaWe",
        ),
    )
    reviewer_name = _first_text(
        card,
        (
            ".d4r55",
            "button.WNxzHc .d4r55",
            "button[aria-label] .d4r55",
        ),
    )
    reviewer_metadata = _first_text(
        card,
        (
            ".RfnDt",
            ".A503be",
            ".WNxzHc + div",
        ),
    )
    translation_label = _first_attribute(
        card,
        (
            "button[aria-label*='translation' i]",
            "button[aria-label*='translate' i]",
        ),
        "aria-label",
    )
    translated_text = _first_text(
        card,
        (
            ".wiI7pd[lang]",
            "span[lang]",
        ),
    )

    row.update(
        {
            "owner_response_date_text": owner_response_date_text or None,
            "approximate_owner_response_date": (
                hardened._relative_date(owner_response_date_text, observed_at=observed_at)
                if owner_response_date_text
                else None
            ),
            "reviewer_name": reviewer_name or None,
            "reviewer_metadata": reviewer_metadata or None,
            "language_translation": {
                "translation_control_label": translation_label or None,
                "translated_text_exposed": translated_text or None,
            },
        }
    )
    return row


def _manual_interruption(page: Any) -> str | None:
    for kind, selector in _MANUAL_INTERRUPTION_SELECTORS:
        try:
            if page.locator(selector).count():
                return kind
        except Exception:
            continue
    return None


def _retry_call(
    operation: Callable[[], Any],
    *,
    page: Any,
    succeeded: Callable[[Any], bool],
    attempts: int = 3,
) -> tuple[Any, int, str | None]:
    last: Any = None
    for attempt in range(1, attempts + 1):
        interruption = _manual_interruption(page)
        if interruption:
            return last, attempt - 1, interruption
        last = operation()
        if succeeded(last):
            return last, attempt, None
        if attempt < attempts:
            try:
                page.wait_for_timeout(400 * attempt)
            except Exception:
                pass
    return last, attempts, None


def retry_click_reviews(page: Any) -> tuple[bool, str, int]:
    result, attempts, interruption = _retry_call(
        lambda: _BASE_CLICK_REVIEWS(page),
        page=page,
        succeeded=lambda value: isinstance(value, tuple) and bool(value[0]),
    )
    if interruption:
        return False, f"manual-interruption:{interruption}", 0
    if not isinstance(result, tuple) or len(result) != 3:
        return False, f"retry-exhausted:{attempts}", 0
    opened, selector, count = result
    if opened:
        return bool(opened), f"retry-{attempts}:{selector}", int(count)
    return False, f"retry-exhausted:{attempts}", int(count)


def retry_choose_sort(page: Any, strategy: str) -> dict[str, object]:
    result, attempts, interruption = _retry_call(
        lambda: _BASE_CHOOSE_SORT(page, strategy),
        page=page,
        succeeded=lambda value: isinstance(value, dict) and value.get("selected") is True,
    )
    if not isinstance(result, dict):
        result = {
            "requested": strategy,
            "selected": False,
            "button_selector": None,
            "option_label": None,
            "fallback": "sort-unavailable",
        }
    output = dict(result)
    output["attempts"] = attempts
    output["manual_interruption"] = interruption
    if interruption:
        output["fallback"] = f"manual-interruption:{interruption}"
    return output


def collect_strategy_with_provenance(
    page: Any,
    *,
    business_name: str,
    strategy: str,
    limit: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows, diagnostics = _BASE_COLLECT_STRATEGY(
        page,
        business_name=business_name,
        strategy=strategy,
        limit=limit,
    )
    source_url = ""
    try:
        source_url = _text(page.url)
    except Exception:
        pass
    for row in rows:
        row["source_url"] = source_url or None
    diagnostics = dict(diagnostics)
    diagnostics["source_url"] = source_url or None
    return rows, diagnostics


def _install_hardened_hooks() -> None:
    hardened._statistics = strategy_safe_statistics
    hardened._review_from_card = review_with_provenance
    hardened._click_reviews = retry_click_reviews
    hardened._choose_sort = retry_choose_sort
    hardened._collect_strategy = collect_strategy_with_provenance


def run(argv: Sequence[str] | None = None) -> int:
    _install_hardened_hooks()
    return hardened.run(argv)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
