from __future__ import annotations

import ipaddress
import socket
from collections import Counter, defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter

from .robots import evaluate_robots_policy


class UnsafeTargetError(ValueError):
    pass


class Status(StrEnum):
    passed = "passed"
    attention = "attention"
    unavailable = "unavailable"


class Finding(BaseModel):
    id: str
    area: str
    title: str
    status: Status
    severity: str
    summary: str
    recommendation: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class Assessment(BaseModel):
    schema_version: str = "1.3"
    target: HttpUrl
    mode: Literal["demo", "live"]
    generated_at: datetime
    elapsed_ms: int
    findings: list[Finding]
    summary: dict[str, int]
    area_summary: dict[str, dict[str, int]]

    @classmethod
    def build(
        cls,
        target: str,
        findings: list[Finding],
        *,
        mode: Literal["demo", "live"] = "live",
        generated_at: datetime | None = None,
        elapsed_ms: int = 0,
    ) -> Assessment:
        status_priority = {
            Status.attention: 0,
            Status.unavailable: 1,
            Status.passed: 2,
        }
        severity_priority = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
            "info": 4,
        }
        ordered = sorted(
            findings,
            key=lambda item: (
                status_priority[item.status],
                severity_priority.get(item.severity.lower(), 5),
                item.area.lower(),
                item.title.lower(),
            ),
        )
        counts = Counter(item.status.value for item in ordered)
        area_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
        for item in ordered:
            area_counts[item.area][item.status.value] += 1
            area_counts[item.area]["total"] += 1
        area_summary = {
            area: {
                "passed": values.get("passed", 0),
                "attention": values.get("attention", 0),
                "unavailable": values.get("unavailable", 0),
                "total": values.get("total", 0),
            }
            for area, values in sorted(area_counts.items())
        }
        return cls(
            target=TypeAdapter(HttpUrl).validate_python(target),
            mode=mode,
            generated_at=generated_at or datetime.now(UTC),
            elapsed_ms=max(0, elapsed_ms),
            findings=ordered,
            summary={
                "passed": counts.get("passed", 0),
                "attention": counts.get("attention", 0),
                "unavailable": counts.get("unavailable", 0),
                "total": len(ordered),
            },
            area_summary=area_summary,
        )


def normalize_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise UnsafeTargetError("A target URL is required.")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeTargetError("Only HTTP and HTTPS URLs with a hostname are supported.")
    if parsed.username or parsed.password:
        raise UnsafeTargetError("Credentials in target URLs are not allowed.")
    return parsed._replace(fragment="").geturl()


def resolve_public_ips(hostname: str) -> list[str]:
    try:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeTargetError(f"The hostname could not be resolved: {hostname}") from exc
    values = sorted({str(record[4][0]) for record in records})
    if not values:
        raise UnsafeTargetError("The hostname resolved to no addresses.")
    for value in values:
        if not ipaddress.ip_address(value).is_global:
            raise UnsafeTargetError(f"Non-public target address is not allowed: {value}")
    return values


_TRUST_LINK_TERMS = {
    "about": ("about", "company", "who-we-are", "who we are"),
    "contact": ("contact", "get-in-touch", "get in touch"),
    "privacy": ("privacy", "data-protection", "data protection"),
    "terms": ("terms", "conditions", "legal"),
}


class _Signals(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = False
        self.viewport = False
        self.canonical = False
        self.json_ld = False
        self.h1 = False
        self.noindex = False
        self.mixed_content = False
        self.language = ""
        self.meta_description = False
        self.og_title = False
        self.og_description = False
        self.trust_links: set[str] = set()
        self._anchor_href: str | None = None

    def _record_trust_link(self, value: str) -> None:
        normalized = value.lower()
        for signal, terms in _TRUST_LINK_TERMS.items():
            if any(term in normalized for term in terms):
                self.trust_links.add(signal)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        lowered = {key: value.lower() for key, value in data.items()}
        if tag == "html":
            self.language = data.get("lang", "").strip()
        if tag == "title":
            self.title = True
        if tag == "h1":
            self.h1 = True
        if tag == "meta" and lowered.get("name") == "viewport":
            self.viewport = True
        if tag == "meta" and lowered.get("name") == "description":
            self.meta_description = bool(data.get("content", "").strip())
        if tag == "meta" and lowered.get("name") == "robots":
            self.noindex = "noindex" in lowered.get("content", "")
        if tag == "meta" and lowered.get("property") == "og:title":
            self.og_title = bool(data.get("content", "").strip())
        if tag == "meta" and lowered.get("property") == "og:description":
            self.og_description = bool(data.get("content", "").strip())
        if tag == "link" and "canonical" in lowered.get("rel", ""):
            self.canonical = True
        if tag == "script" and lowered.get("type") == "application/ld+json":
            self.json_ld = True
        if tag == "a":
            self._anchor_href = data.get("href", "")
            self._record_trust_link(self._anchor_href)
        for attribute in ("src", "href"):
            if lowered.get(attribute, "").startswith("http://"):
                self.mixed_content = True

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._record_trust_link(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._anchor_href = None


def _finding(
    identifier: str,
    area: str,
    title: str,
    ok: bool,
    recommendation: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        id=identifier,
        area=area,
        title=title,
        status=Status.passed if ok else Status.attention,
        severity="info" if ok else "medium",
        summary=f"{title} is {'present' if ok else 'absent'}.",
        recommendation=None if ok else recommendation,
        evidence=evidence or {},
    )


def _crawler_finding(robots: str, user_agent: str, title: str) -> Finding:
    policy = evaluate_robots_policy(robots, user_agent)
    allowed = not policy.disallow_all
    return Finding(
        id=f"ai.{user_agent.lower()}",
        area="AI discoverability" if user_agent != "Googlebot" else "Search visibility",
        title=title,
        status=Status.passed if allowed else Status.attention,
        severity="info" if allowed else "medium",
        summary=f"{title} is {'allowed' if allowed else 'blocked'} by robots.txt.",
        recommendation=None if allowed else "Review robots.txt if this crawler should access public content.",
        evidence={"matched_group": policy.matched_group, "disallow_all": policy.disallow_all},
    )


def analyze_document(html: str, headers: dict[str, str], robots: str = "") -> list[Finding]:
    parser = _Signals()
    parser.feed(html)
    lower_headers = {key.lower(): value for key, value in headers.items()}
    frame_protection = (
        "x-frame-options" in lower_headers
        or "frame-ancestors" in lower_headers.get("content-security-policy", "").lower()
    )
    sitemap_urls = [
        line.split(":", 1)[1].strip()
        for line in robots.splitlines()
        if line.strip().lower().startswith("sitemap:") and ":" in line
    ]
    findings = [
        _finding("health.title", "Website health", "Document title", parser.title, "Add a descriptive title."),
        _finding("health.viewport", "Website health", "Mobile viewport", parser.viewport, "Add a viewport meta tag."),
        _finding("health.language", "Website health", "HTML language declaration", bool(parser.language), "Declare the page language on the html element.", evidence={"language": parser.language}),
        _finding("search.description", "Search visibility", "Meta description", parser.meta_description, "Add a concise, page-specific meta description."),
        _finding("search.canonical", "Search visibility", "Canonical URL", parser.canonical, "Add a self-referencing canonical URL."),
        _finding("search.indexable", "Search visibility", "Indexable robots meta", not parser.noindex, "Remove noindex when the page should appear in search."),
        _finding("search.sitemap", "Search visibility", "Sitemap declaration", bool(sitemap_urls), "Declare the XML sitemap in robots.txt.", evidence={"sitemaps": sitemap_urls}),
        _finding("ai.structured-data", "AI discoverability", "Structured entity data", parser.json_ld, "Add accurate Organisation or Service JSON-LD."),
        _finding("ai.open-graph-title", "AI discoverability", "Open Graph title", parser.og_title, "Add an accurate og:title value."),
        _finding("ai.open-graph-description", "AI discoverability", "Open Graph description", parser.og_description, "Add an accurate og:description value."),
        _finding("trust.heading", "Trust signals", "Primary heading", parser.h1, "Add one clear primary heading."),
        _finding("trust.about", "Trust signals", "About link", "about" in parser.trust_links, "Link clearly to information about the organisation.", evidence={"detected_link_types": sorted(parser.trust_links)}),
        _finding("trust.contact", "Trust signals", "Contact link", "contact" in parser.trust_links, "Provide a clearly labelled contact route.", evidence={"detected_link_types": sorted(parser.trust_links)}),
        _finding("trust.privacy", "Trust signals", "Privacy link", "privacy" in parser.trust_links, "Link clearly to a privacy or data-protection notice.", evidence={"detected_link_types": sorted(parser.trust_links)}),
        _finding("trust.terms", "Trust signals", "Terms link", "terms" in parser.trust_links, "Link clearly to applicable terms or legal information.", evidence={"detected_link_types": sorted(parser.trust_links)}),
        _finding("security.hsts", "Security posture", "Strict-Transport-Security", "strict-transport-security" in lower_headers, "Deploy HSTS after HTTPS validation."),
        _finding("security.csp", "Security posture", "Content-Security-Policy", "content-security-policy" in lower_headers, "Introduce and test a CSP."),
        _finding("security.nosniff", "Security posture", "X-Content-Type-Options", lower_headers.get("x-content-type-options", "").lower() == "nosniff", "Set X-Content-Type-Options: nosniff."),
        _finding("security.frames", "Security posture", "Frame protection", frame_protection, "Set frame-ancestors in CSP or X-Frame-Options."),
        _finding("security.referrer", "Security posture", "Referrer-Policy", "referrer-policy" in lower_headers, "Set an appropriate Referrer-Policy."),
        _finding("security.permissions", "Security posture", "Permissions-Policy", "permissions-policy" in lower_headers, "Set a restrictive Permissions-Policy where appropriate."),
        _finding("security.mixed-content", "Security posture", "No obvious mixed content", not parser.mixed_content, "Replace HTTP asset references with HTTPS."),
        _crawler_finding(robots, "OAI-SearchBot", "OAI-SearchBot access"),
        _crawler_finding(robots, "GPTBot", "GPTBot access"),
        _crawler_finding(robots, "Google-Extended", "Google-Extended access"),
        _crawler_finding(robots, "Googlebot", "Googlebot access"),
    ]
    return findings


def demo_assessment() -> Assessment:
    html = "<html lang='en'><head><title>Demo</title><meta name='viewport' content='width=device-width'><meta name='description' content='Demo'><meta property='og:title' content='Demo'><meta property='og:description' content='Demo'></head><body><h1>Demo</h1><a href='/about'>About</a><a href='/contact'>Contact</a><a href='/privacy'>Privacy</a><a href='/terms'>Terms</a></body></html>"
    return Assessment.build(
        "https://demo.veridra.local",
        analyze_document(html, {"x-content-type-options": "nosniff"}, "Sitemap: https://demo.veridra.local/sitemap.xml"),
        mode="demo",
    )
