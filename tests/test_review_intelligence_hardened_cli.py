from datetime import UTC, datetime
from typing import Any

from veridra.review_intelligence_hardened_cli import (
    _choose_sort,
    _review_cards,
    _review_from_card,
    _success_state,
)


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

    @property
    def last(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return self._count

    def inner_text(self, timeout: int = 0) -> str:
        _ = timeout
        return self._text

    def get_attribute(self, name: str) -> str | None:
        return self._attributes.get(name)

    def click(self, timeout: int = 0) -> None:
        _ = timeout


class FakeCard:
    def __init__(self) -> None:
        self._nodes: dict[str, FakeLocator] = {
            ".MyEned .wiI7pd": FakeLocator(count=1, text="Very helpful and friendly staff."),
            "span.kvMYJc": FakeLocator(count=1, attributes={"aria-label": "5 stars"}),
            ".rsqaWe": FakeLocator(count=1, text="2 weeks ago"),
            ".CDe7pd .wiI7pd": FakeLocator(count=1, text="Thank you for your feedback."),
        }

    def get_attribute(self, name: str) -> str | None:
        if name == "data-review-id":
            return "review-123"
        return None

    def locator(self, selector: str) -> FakeLocator:
        return self._nodes.get(selector, FakeLocator())


class FakeKeyboard:
    def press(self, key: str) -> None:
        _ = key


class FakePage:
    def __init__(self, selectors: dict[str, FakeLocator] | None = None) -> None:
        self._selectors = selectors or {}
        self.keyboard = FakeKeyboard()

    def locator(self, selector: str) -> FakeLocator:
        return self._selectors.get(selector, FakeLocator())

    def get_by_role(self, *_args: Any, **_kwargs: Any) -> FakeLocator:
        return FakeLocator()

    def get_by_text(self, *_args: Any, **_kwargs: Any) -> FakeLocator:
        return FakeLocator()

    def wait_for_timeout(self, timeout: int) -> None:
        _ = timeout


def test_live_review_card_shape_is_extracted() -> None:
    observed_at = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
    row = _review_from_card(
        FakeCard(),
        business_name="Example Dental",
        strategy="newest",
        observed_at=observed_at,
    )

    assert row is not None
    assert row["source_review_id"] == "review-123"
    assert row["rating"] == 5
    assert row["text"] == "Very helpful and friendly staff."
    assert row["approximate_review_date"] == "2026-08-12"
    assert row["owner_response_present"] is True
    assert row["owner_response_text"] == "Thank you for your feedback."


def test_review_card_selector_accepts_current_jftief_shape() -> None:
    page = FakePage(
        {
            "div.jftiEf[data-review-id]": FakeLocator(count=7),
        }
    )
    _cards, selector, count = _review_cards(page)
    assert selector == "div.jftiEf[data-review-id]"
    assert count == 7


def test_sort_failure_is_not_mislabeled_as_newest() -> None:
    page = FakePage()
    newest = _choose_sort(page, "newest")
    lowest = _choose_sort(page, "lowest")

    assert newest["selected"] is False
    assert newest["fallback"] == "visible-current-order"
    assert lowest["selected"] is False
    assert lowest["fallback"] == "sort-unavailable"


def test_empty_review_sample_is_a_failure_state() -> None:
    assert _success_state([]) == "review_evidence_empty"
    assert _success_state([{"evidence_id": "review:x:1"}]) == "review_evidence_collected"
