from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .core import Finding, Status

_LOCAL_TYPES = {
    "localbusiness",
    "automotivebusiness",
    "dentist",
    "employmentagency",
    "entertainmentbusiness",
    "financialservice",
    "foodestablishment",
    "governmentoffice",
    "healthandbeautybusiness",
    "homeandconstructionbusiness",
    "internetbusiness",
    "legalservice",
    "library",
    "lodgingbusiness",
    "medicalbusiness",
    "professionalservice",
    "radio station",
    "realestateagent",
    "recyclingcenter",
    "selfstorage",
    "shoppingcenter",
    "sportsactivitylocation",
    "store",
    "televisionstation",
    "touristattraction",
    "travelagency",
}
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_POSTAL_RE = re.compile(
    r"\b(?:[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}|\d{5}(?:-\d{4})?|\d{4,6})\b",
    re.IGNORECASE,
)
_HOURS_RE = re.compile(
    r"\b(?:opening hours?|business hours?|hours today|mon(?:day)?\s*[-–]|"
    r"tue(?:sday)?\s*[-–]|wed(?:nesday)?\s*[-–]|thu(?:rsday)?\s*[-–]|"
    r"fri(?:day)?\s*[-–]|sat(?:urday)?\s*[-–]|sun(?:day)?\s*[-–])",
    re.IGNORECASE,
)
_LOCATION_TERMS = (
    "locations",
    "location",
    "find-us",
    "find us",
    "where-we-are",
    "where we are",
    "directions",
    "visit-us",
    "visit us",
)
_MAP_HOSTS = (
    "google.com",
    "google.es",
    "maps.google",
    "goo.gl",
    "apple.com",
    "bing.com",
    "openstreetmap.org",
    "waze.com",
)


@dataclass
class LocalSignals:
    json_ld_payloads: list[str] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)
    hrefs: list[str] = field(default_factory=list)
    address_element: bool = False
    location_link: bool = False


class _LocalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.signals = LocalSignals()
        self._json_ld = False
        self._json_buffer: list[str] = []
        self._anchor_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        lowered = {key: value.lower() for key, value in data.items()}
        if tag == "script" and lowered.get("type") == "application/ld+json":
            self._json_ld = True
            self._json_buffer = []
        if tag == "address":
            self.signals.address_element = True
        if tag == "a":
            href = data.get("href", "").strip()
            self._anchor_href = href
            if href:
                self.signals.hrefs.append(href)
                self._record_location_term(href)

    def handle_data(self, data: str) -> None:
        if self._json_ld:
            self._json_buffer.append(data)
            return
        normalized = " ".join(data.split())
        if normalized:
            self.signals.text_parts.append(normalized)
            if self._anchor_href is not None:
                self._record_location_term(normalized)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_ld:
            payload = "".join(self._json_buffer).strip()
            if payload:
                self.signals.json_ld_payloads.append(payload)
            self._json_ld = False
            self._json_buffer = []
        if tag == "a":
            self._anchor_href = None

    def _record_location_term(self, value: str) -> None:
        lowered = value.lower()
        if any(term in lowered for term in _LOCATION_TERMS):
            self.signals.location_link = True


def _iter_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_nodes(child)


def _types(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    return {str(item).strip().lower() for item in values if item}


def _is_local_node(node: dict[str, Any]) -> bool:
    values = _types(node)
    return bool(values & _LOCAL_TYPES) or "localbusiness" in values


def _structured_nodes(payloads: list[str]) -> tuple[list[dict[str, Any]], int]:
    nodes: list[dict[str, Any]] = []
    invalid = 0
    for payload in payloads:
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            invalid += 1
            continue
        nodes.extend(node for node in _iter_nodes(decoded) if _is_local_node(node))
    return nodes, invalid


def _has_value(nodes: list[dict[str, Any]], *keys: str) -> bool:
    return any(any(node.get(key) not in (None, "", [], {}) for key in keys) for node in nodes)


def _map_link(hrefs: list[str]) -> bool:
    for href in hrefs:
        parsed = urlparse(href if "://" in href else f"https://placeholder.invalid/{href}")
        host = (parsed.hostname or "").lower()
        lowered = href.lower()
        if any(candidate in host for candidate in _MAP_HOSTS):
            return True
        if "maps" in lowered or "directions" in lowered:
            return True
    return False


def _finding(
    identifier: str,
    title: str,
    ok: bool,
    recommendation: str,
    *,
    evidence: dict[str, Any],
) -> Finding:
    return Finding(
        id=identifier,
        area="Local presence",
        title=title,
        status=Status.passed if ok else Status.attention,
        severity="info" if ok else "medium",
        summary=f"{title} is {'present' if ok else 'not evident'} on the assessed website.",
        recommendation=None if ok else recommendation,
        evidence=evidence,
    )


def analyze_local_readiness(document: str) -> list[Finding]:
    parser = _LocalParser()
    parser.feed(document)
    signals = parser.signals
    text = " ".join(signals.text_parts)
    nodes, invalid_json_ld = _structured_nodes(signals.json_ld_payloads)
    detected_types = sorted({item for node in nodes for item in _types(node)})

    visible_phone = bool(_PHONE_RE.search(text)) or any(
        href.lower().startswith("tel:") for href in signals.hrefs
    )
    visible_address = signals.address_element or bool(_POSTAL_RE.search(text))
    visible_hours = bool(_HOURS_RE.search(text))
    map_link = _map_link(signals.hrefs)
    location_route = signals.location_link
    common_evidence = {
        "local_business_nodes": len(nodes),
        "detected_types": detected_types,
        "invalid_json_ld_blocks": invalid_json_ld,
    }

    return [
        _finding(
            "local.structured-business",
            "LocalBusiness structured data",
            bool(nodes),
            "Add accurate LocalBusiness JSON-LD using the most specific applicable subtype.",
            evidence=common_evidence,
        ),
        _finding(
            "local.structured-name",
            "Structured business name",
            _has_value(nodes, "name"),
            "Add the public business name to LocalBusiness structured data.",
            evidence=common_evidence,
        ),
        _finding(
            "local.structured-url",
            "Structured website URL",
            _has_value(nodes, "url"),
            "Add the canonical public website URL to LocalBusiness structured data.",
            evidence=common_evidence,
        ),
        _finding(
            "local.structured-phone",
            "Structured telephone",
            _has_value(nodes, "telephone"),
            "Add the primary public telephone number to LocalBusiness structured data.",
            evidence=common_evidence,
        ),
        _finding(
            "local.structured-address",
            "Structured postal address",
            _has_value(nodes, "address"),
            "Add a complete PostalAddress to LocalBusiness structured data.",
            evidence=common_evidence,
        ),
        _finding(
            "local.structured-hours",
            "Structured opening hours",
            _has_value(nodes, "openingHours", "openingHoursSpecification"),
            "Add accurate openingHours or openingHoursSpecification data.",
            evidence=common_evidence,
        ),
        _finding(
            "local.structured-same-as",
            "Structured profile references",
            _has_value(nodes, "sameAs"),
            "Add verified public profile URLs through sameAs where appropriate.",
            evidence=common_evidence,
        ),
        _finding(
            "local.visible-phone",
            "Visible telephone route",
            visible_phone,
            "Publish a clear, clickable public telephone number where customers expect it.",
            evidence={"telephone_detected": visible_phone},
        ),
        _finding(
            "local.visible-address",
            "Visible address signal",
            visible_address,
            "Publish the business address or clearly explain the service area.",
            evidence={
                "address_element": signals.address_element,
                "postal_pattern_detected": bool(_POSTAL_RE.search(text)),
            },
        ),
        _finding(
            "local.visible-hours",
            "Visible opening-hours signal",
            visible_hours,
            "Publish accurate opening hours or availability information.",
            evidence={"opening_hours_language_detected": visible_hours},
        ),
        _finding(
            "local.map-link",
            "Map or directions route",
            map_link,
            "Provide a clear map or directions link for customers visiting the location.",
            evidence={"map_link_detected": map_link},
        ),
        _finding(
            "local.location-route",
            "Location information route",
            location_route,
            "Add a clearly labelled location, directions, or find-us route.",
            evidence={"location_link_detected": location_route},
        ),
    ]
