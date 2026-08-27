from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class GbpProfileEvidence(BaseModel):
    """Public Google Business Profile evidence captured from a visible Maps detail page."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    business_name: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    collection_status: str = Field(default="ok", max_length=80)
    category: str = Field(default="", max_length=160)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    website_url: HttpUrl | None = None
    address_text: str = Field(default="", max_length=1000)
    phone_text: str = Field(default="", max_length=500)
    hours_text: str = Field(default="", max_length=2000)
    booking_links: tuple[HttpUrl, ...] = Field(default=(), max_length=30)
    external_action_links: tuple[HttpUrl, ...] = Field(default=(), max_length=100)
    profile_item_ids: tuple[str, ...] = Field(default=(), max_length=500)
    photo_control_labels: tuple[str, ...] = Field(default=(), max_length=200)
    raw_action_labels: tuple[str, ...] = Field(default=(), max_length=300)
    coverage_note: str = Field(
        default=(
            "Fields describe what the public Google Maps detail page exposed during this "
            "bounded observation. An unobserved field is not by itself proof that the business "
            "owner failed to configure it."
        ),
        max_length=1000,
    )


_BOOKING_TERMS = (
    "appointment",
    "appointments",
    "book",
    "booking",
    "reserve",
    "reservation",
    "schedule",
)


def external_http_url(value: str, *, google_host: str = "google") -> str | None:
    """Return an external HTTP(S) URL, excluding Google-owned navigation links."""

    candidate = value.strip()
    if not candidate.startswith(("http://", "https://")):
        return None
    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").casefold().strip(".")
    if not host:
        return None
    if host.startswith(f"{google_host}.") or f".{google_host}." in host:
        return None
    if host.endswith("google.com") or host.endswith("googleusercontent.com"):
        return None
    return candidate


def classify_booking_links(
    links: list[tuple[str, str, str]],
) -> tuple[str, ...]:
    """Classify externally hosted appointment/booking actions from observable labels/item IDs."""

    found: list[str] = []
    for href, label, item_id in links:
        external = external_http_url(href)
        if external is None:
            continue
        haystack = f"{label} {item_id}".casefold()
        if not any(term in haystack for term in _BOOKING_TERMS):
            continue
        if external not in found:
            found.append(external)
    return tuple(found)


def unique_external_links(links: list[tuple[str, str, str]]) -> tuple[str, ...]:
    found: list[str] = []
    for href, _label, _item_id in links:
        external = external_http_url(href)
        if external is not None and external not in found:
            found.append(external)
    return tuple(found)
