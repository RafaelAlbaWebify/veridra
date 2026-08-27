from __future__ import annotations

from veridra.assisted_google_maps import (
    _advance_results_feed,
    _canonical_maps_identity,
    _clean_category,
    _external_website,
    _provider_key,
)


class _Card:
    def __init__(self) -> None:
        self.scrolled = False
        self.hovered = False

    def scroll_into_view_if_needed(self, *, timeout: int) -> None:
        assert timeout == 2_000
        self.scrolled = True

    def hover(self, *, timeout: int) -> None:
        assert timeout == 2_000
        self.hovered = True


class _Cards:
    def __init__(self, cards: list[_Card]) -> None:
        self.cards = cards

    def count(self) -> int:
        return len(self.cards)

    def nth(self, index: int) -> _Card:
        return self.cards[index]


class _Mouse:
    def __init__(self) -> None:
        self.wheels: list[tuple[int, int]] = []

    def wheel(self, x: int, y: int) -> None:
        self.wheels.append((x, y))


class _Page:
    def __init__(self, cards: list[_Card]) -> None:
        self.cards = _Cards(cards)
        self.mouse = _Mouse()
        self.waits: list[int] = []

    def locator(self, selector: str) -> _Cards:
        assert selector == '[role="feed"] [role="article"]'
        return self.cards

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


class _Feed:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def evaluate(self, script: str) -> None:
        self.scripts.append(script)


def test_same_google_place_identity_survives_url_variants() -> None:
    sponsored = (
        "https://www.google.com/maps/place/Slievemore+Dental/"
        "data=!4m7!3m6!1s0x4867091e23065b7f:0x433908020e736b82!8m2!3d53.2924936!4d-6.2010661"
        "?authuser=0&hl=en&rclk=1"
    )
    organic = (
        "https://www.google.com/maps/place/Slievemore+Dental/"
        "data=!4m7!3m6!1s0x4867091e23065b7f:0x433908020e736b82!8m2!3d53.2924936!4d-6.2010661"
        "?entry=ttu&g_ep=test"
    )

    sponsored_identity = _canonical_maps_identity(sponsored, name="Slievemore Dental")
    organic_identity = _canonical_maps_identity(organic, name="Slievemore Dental")
    assert sponsored_identity == organic_identity
    assert _provider_key(sponsored, name="Slievemore Dental") == _provider_key(
        organic,
        name="Slievemore Dental",
    )


def test_google_redirect_can_reveal_real_external_website() -> None:
    wrapped = "https://www.google.com/url?q=https%3A%2F%2Fslievemoredental.ie%2F&sa=U"

    assert _external_website(wrapped) == "https://slievemoredental.ie/"
    assert _external_website("https://www.google.ie/maps/place/example") is None


def test_category_cleanup_rejects_non_categories() -> None:
    assert _clean_category("Slievemore Dental", name="Slievemore Dental") == ""
    assert _clean_category("Sponsored", name="Slievemore Dental") == ""
    assert _clean_category("  Emergency dental service  ", name="Slievemore Dental") == (
        "Emergency dental service"
    )


def test_virtualized_feed_advancement_uses_last_card_and_wheel() -> None:
    cards = [_Card(), _Card(), _Card()]
    page = _Page(cards)
    feed = _Feed()

    _advance_results_feed(page, feed)

    assert cards[-1].scrolled is True
    assert cards[-1].hovered is True
    assert page.mouse.wheels == [(0, 1_200)]
    assert len(feed.scripts) == 1
    assert "scrollBy" in feed.scripts[0]
    assert page.waits == [1_000]
