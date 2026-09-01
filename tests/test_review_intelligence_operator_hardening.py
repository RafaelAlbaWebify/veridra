from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import veridra.review_intelligence_sampling_safe_cli as safe


class FakeLocator:
    def __init__(
        self,
        *,
        count: int = 0,
        text: str = "",
        attributes: dict[str, str] | None = None,
    ) -> None:
        self._count = count
        self._text = text
        self._attributes = attributes or {}

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return self._count

    def inner_text(self, timeout: int = 0) -> str:
        _ = timeout
        return self._text

    def get_attribute(self, name: str) -> str | None:
        return self._attributes.get(name)


class FakeCard:
    def __init__(self) -> None:
        self._nodes = {
            ".CDe7pd .rsqaWe": FakeLocator(count=1, text="3 days ago"),
            ".d4r55": FakeLocator(count=1, text="Local Reviewer"),
            ".RfnDt": FakeLocator(count=1, text="Local Guide · 42 reviews"),
            "button[aria-label*='translation' i]": FakeLocator(
                count=1,
                attributes={"aria-label": "See translation"},
            ),
            ".wiI7pd[lang]": FakeLocator(count=1, text="Translated review text"),
        }

    def locator(self, selector: str) -> FakeLocator:
        return self._nodes.get(selector, FakeLocator())


class FakePage:
    def __init__(self, *, selectors: dict[str, int] | None = None) -> None:
        self._selectors = selectors or {}
        self.url = "https://www.google.com/maps/place/example"
        self.waits: list[int] = []

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(count=self._selectors.get(selector, 0))

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


def test_review_provenance_adds_optional_metadata(monkeypatch: Any) -> None:
    observed_at = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    base_row: dict[str, object] = {
        "evidence_id": "review:example:123",
        "rating": 5,
        "text": "Great visit",
        "owner_response_present": True,
    }
    monkeypatch.setattr(safe, "_BASE_REVIEW_FROM_CARD", lambda *_args, **_kwargs: dict(base_row))

    row = safe.review_with_provenance(
        FakeCard(),
        business_name="Example Dental",
        strategy="newest",
        observed_at=observed_at,
    )

    assert row is not None
    assert row["reviewer_name"] == "Local Reviewer"
    assert row["reviewer_metadata"] == "Local Guide · 42 reviews"
    assert row["owner_response_date_text"] == "3 days ago"
    assert row["approximate_owner_response_date"] == "2026-08-29"
    language = row["language_translation"]
    assert isinstance(language, dict)
    assert language["translation_control_label"] == "See translation"
    assert language["translated_text_exposed"] == "Translated review text"


def test_retry_click_reviews_recovers_transient_failure(monkeypatch: Any) -> None:
    calls = 0

    def fake_click(_page: object) -> tuple[bool, str, int]:
        nonlocal calls
        calls += 1
        if calls < 3:
            return False, "", 0
        return True, "reviews-button", 4

    monkeypatch.setattr(safe, "_BASE_CLICK_REVIEWS", fake_click)
    result = safe.retry_click_reviews(FakePage())

    assert calls == 3
    assert result == (True, "retry-3:reviews-button", 4)


def test_manual_interruption_prevents_automated_retry(monkeypatch: Any) -> None:
    calls = 0

    def fake_click(_page: object) -> tuple[bool, str, int]:
        nonlocal calls
        calls += 1
        return False, "", 0

    monkeypatch.setattr(safe, "_BASE_CLICK_REVIEWS", fake_click)
    page = FakePage(selectors={"iframe[src*='recaptcha']": 1})

    result = safe.retry_click_reviews(page)

    assert calls == 0
    assert result == (False, "manual-interruption:captcha", 0)


def test_collect_strategy_attaches_source_url(monkeypatch: Any) -> None:
    def fake_collect(
        _page: object,
        *,
        business_name: str,
        strategy: str,
        limit: int,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        _ = business_name, strategy, limit
        return [{"evidence_id": "review:example:1"}], {"rows_collected": 1}

    monkeypatch.setattr(safe, "_BASE_COLLECT_STRATEGY", fake_collect)
    rows, diagnostics = safe.collect_strategy_with_provenance(
        FakePage(),
        business_name="Example Dental",
        strategy="newest",
        limit=5,
    )

    assert rows[0]["source_url"] == "https://www.google.com/maps/place/example"
    assert diagnostics["source_url"] == "https://www.google.com/maps/place/example"


def test_sort_retry_exposes_attempt_count(monkeypatch: Any) -> None:
    calls = 0

    def fake_sort(_page: object, strategy: str) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "requested": strategy,
            "selected": calls == 2,
            "button_selector": "sort-button" if calls == 2 else None,
            "option_label": "Newest" if calls == 2 else None,
            "fallback": None,
        }

    monkeypatch.setattr(safe, "_BASE_CHOOSE_SORT", fake_sort)
    result = safe.retry_choose_sort(FakePage(), "newest")

    assert calls == 2
    assert result["selected"] is True
    assert result["attempts"] == 2
    assert result["manual_interruption"] is None
