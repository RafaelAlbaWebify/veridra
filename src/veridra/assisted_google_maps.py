from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import Any

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


def _provider_key(source_url: str | None, *, name: str, index: int) -> str:
    identity = source_url or f"{name.casefold()}|{index}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"google-maps:{digest}"


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
        for link_index in range(int(links.count())):
            href = links.nth(link_index).get_attribute("href")
            if not isinstance(href, str) or not href:
                continue
            if "/maps/place/" in href and source_url is None:
                source_url = href
            elif href.startswith("http") and "google." not in href and website is None:
                website = href

        captured.append(
            ObservedBusiness.model_validate(
                {
                    "provider": "assisted-google-maps",
                    "provider_key": _provider_key(source_url, name=name, index=index),
                    "name": name,
                    "category": lines[1] if len(lines) > 1 else "",
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
