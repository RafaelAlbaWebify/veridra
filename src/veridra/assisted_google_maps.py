from __future__ import annotations

import hashlib
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urlsplit

from .assisted_discovery import (
    BoundedDiscoveryLimits,
    OrderedObservationAccumulator,
    TraversalResult,
)
from .prospect_discovery import ObservedBusiness

_END_OF_LIST_MARKERS = (
    "you've reached the end of the list",
    "you have reached the end of the list",
)
_GOOGLE_PLACE_ID_PATTERN = re.compile(r"!1s([^!/?&]+)")
_DETAIL_WEBSITE_SELECTOR = 'a[data-item-id="authority"][href]'
_DETAIL_CATEGORY_SELECTORS = (
    'button[jsaction*="category"]',
    '[data-item-id="category"]',
)


class VisiblePageUnsupported(RuntimeError):
    pass


class VisiblePageSelectorDrift(RuntimeError):
    pass


def _feed_has_end_marker(feed: Any) -> bool:
    try:
        text = str(feed.inner_text(timeout=1_000)).casefold()
    except Exception:
        return False
    return any(marker in text for marker in _END_OF_LIST_MARKERS)


def _canonical_maps_identity(source_url: str | None, *, name: str) -> str:
    if source_url:
        match = _GOOGLE_PLACE_ID_PATTERN.search(source_url)
        if match:
            return f"place-id:{unquote(match.group(1)).casefold()}"
        parsed = urlsplit(source_url)
        path = unquote(parsed.path)
        if "/maps/place/" in path:
            place_path = path.split("/data=", 1)[0].rstrip("/")
            return f"place-path:{place_path.casefold()}"
    return f"name:{' '.join(name.casefold().split())}"


def _provider_key(source_url: str | None, *, name: str) -> str:
    identity = _canonical_maps_identity(source_url, name=name)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"google-maps:{digest}"


def _external_website(href: str | None) -> str | None:
    if not isinstance(href, str) or not href.startswith(("http://", "https://")):
        return None
    hostname = (urlsplit(href).hostname or "").casefold()
    if hostname == "google.com" or hostname.endswith(".google.com"):
        return None
    return href


def _clean_category(value: str, *, name: str) -> str:
    clean = " ".join(value.split()).strip()
    if not clean:
        return ""
    if clean.casefold() in {name.casefold(), "sponsored", "ad", "advertisement"}:
        return ""
    return clean


def _detail_panel_metadata(page: Any, place_link: Any, *, name: str) -> tuple[str | None, str]:
    try:
        place_link.click(timeout=2_500)
        page.wait_for_timeout(450)
    except Exception:
        return None, ""

    website: str | None = None
    try:
        website_locator = page.locator(_DETAIL_WEBSITE_SELECTOR)
        if int(website_locator.count()) > 0:
            website = _external_website(website_locator.first.get_attribute("href"))
    except Exception:
        website = None

    category = ""
    for selector in _DETAIL_CATEGORY_SELECTORS:
        try:
            locator = page.locator(selector)
            if int(locator.count()) == 0:
                continue
            candidate = _clean_category(str(locator.first.inner_text(timeout=1_000)), name=name)
            if candidate:
                category = candidate
                break
        except Exception:
            continue
    return website, category


def capture_visible_google_maps_businesses(
    page: Any,
    *,
    max_results: int,
    country_code: str,
    locality: str = "",
    administrative_area: str = "",
) -> list[ObservedBusiness]:
    if max_results < 1:
        raise ValueError("max_results must be at least 1.")
    clean_country = country_code.strip().upper()
    if len(clean_country) != 2:
        raise ValueError("country_code must contain exactly two characters.")
    page_url = str(page.url)
    if "google." not in page_url or "/maps" not in page_url:
        raise VisiblePageUnsupported(
            "Open a supported Google Maps results page in the visible browser and retry."
        )

    cards = page.locator('[role="feed"] [role="article"]')
    count = min(int(cards.count()), max_results)
    if count == 0:
        raise VisiblePageSelectorDrift(
            "No visible Google Maps result cards were found. Confirm the results panel is open "
            "and retry; the page structure may have changed."
        )

    captured: list[ObservedBusiness] = []
    observed_at = datetime.now(UTC)
    for index in range(count):
        card = cards.nth(index)
        text = str(card.inner_text(timeout=2_000)).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        name = lines[0] if lines else ""
        if not name:
            continue

        links = card.locator("a[href]")
        source_url: str | None = None
        website: str | None = None
        place_link: Any | None = None
        for link_index in range(int(links.count())):
            link = links.nth(link_index)
            href = link.get_attribute("href")
            if not isinstance(href, str) or not href:
                continue
            if "/maps/place/" in href and source_url is None:
                source_url = href
                place_link = link
                continue
            external = _external_website(href)
            if external is not None and website is None:
                website = external

        category = ""
        if len(lines) > 1:
            category = _clean_category(lines[1], name=name)

        if place_link is not None and (website is None or not category):
            detail_website, detail_category = _detail_panel_metadata(
                page,
                place_link,
                name=name,
            )
            if website is None:
                website = detail_website
            if not category:
                category = detail_category

        captured.append(
            ObservedBusiness.model_validate(
                {
                    "provider": "assisted-google-maps",
                    "provider_key": _provider_key(source_url, name=name),
                    "name": name,
                    "category": category,
                    "locality": locality,
                    "administrative_area": administrative_area,
                    "country_code": clean_country,
                    "website": website,
                    "source_url": source_url,
                    "observed_at": observed_at,
                }
            )
        )
    return captured


def traverse_google_maps_results(
    page: Any,
    *,
    query_text: str,
    query_sequence: int,
    limits: BoundedDiscoveryLimits,
    country_code: str,
    locality: str = "",
    administrative_area: str = "",
) -> TraversalResult:
    page_url = str(page.url)
    if "google." not in page_url or "/maps" not in page_url:
        raise VisiblePageUnsupported(
            "Open a supported Google Maps results page in the visible browser and retry."
        )
    feed = page.locator('[role="feed"]')
    if int(feed.count()) == 0:
        raise VisiblePageSelectorDrift(
            "No Google Maps result panel was found. Confirm the results panel is open and retry."
        )

    accumulator = OrderedObservationAccumulator(
        query_text=query_text,
        query_sequence=query_sequence,
        limits=limits,
    )
    started = time.monotonic()
    scroll_step = 0

    while True:
        elapsed = time.monotonic() - started
        businesses = capture_visible_google_maps_businesses(
            page,
            max_results=limits.max_results,
            country_code=country_code,
            locality=locality,
            administrative_area=administrative_area,
        )
        accumulator.add_batch(businesses, scroll_step=scroll_step)
        stop_reason = accumulator.evaluate_stop(
            scroll_step=scroll_step,
            elapsed_seconds=elapsed,
            end_of_list=_feed_has_end_marker(feed),
        )
        if stop_reason is not None:
            return accumulator.result(
                scroll_step=scroll_step,
                elapsed_seconds=elapsed,
                stop_reason=stop_reason,
            )

        feed.evaluate(
            "(element) => element.scrollBy(0, Math.max(element.clientHeight * 0.8, 500))"
        )
        page.wait_for_timeout(750)
        scroll_step += 1
