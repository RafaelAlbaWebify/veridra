from __future__ import annotations

import ipaddress
import socket
from collections import Counter
from enum import StrEnum
from html.parser import HTMLParser
from typing import Any
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
    schema_version: str = "1.1"
    target: HttpUrl
    findings: list[Finding]
    summary: dict[str, int]

    @classmethod
    def build(cls, target: str, findings: list[Finding]) -> Assessment:
        counts = Counter(item.status.value for item in findings)
        return cls(
            target=TypeAdapter(HttpUrl).validate_python(target),
            findings=findings,
            summary={
                "passed": counts.get("passed", 0),
                "attention": counts.get("attention", 0),
                "unavailable": counts.get("unavailable", 0),
                "total": len(findings),
            },
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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        lowered = {key: value.lower() for key, value in data.items()}
        if tag == "title":
            self.title = True
        if tag == "h1":
            self.h1 = True
        if tag == "meta" and lowered.get("name") == "viewport":
            self.viewport = True
        if tag == "meta" and lowered.get("name") == "robots":
            self.noindex = "noindex" in lowered.get("content", "")
        if tag == "link" and "canonical" in lowered.get("rel", ""):
            self.canonical = True
        if tag == "script" and lowered.get("type") == "application/ld+json":
            self.json_ld = True
        for attribute in ("src", "href"):
            if lowered.get(attribute, "").startswith("http://"):
                self.mixed_content = True


def _finding(identifier: str, area: str, title: str, ok: bool, recommendation: str) -> Finding:
    return Finding(
        id=identifier,
        area=area,
        title=title,
        status=Status.passed if ok else Status.attention,
        severity="info" if ok else "medium",
        summary=f"{title} is {'present' if ok else 'absent'}.",
        recommendation=None if ok else recommendation,
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
    findings = [
        _finding("health.title", "Website health", "Document title", parser.title, "Add a descriptive title."),
        _finding("health.viewport", "Website health", "Mobile viewport", parser.viewport, "Add a viewport meta tag."),
        _finding("search.canonical", "Search visibility", "Canonical URL", parser.canonical, "Add a self-referencing canonical URL."),
        _finding("search.indexable", "Search visibility", "Indexable robots meta", not parser.noindex, "Remove noindex when the page should appear in search."),
        _finding("ai.structured-data", "AI discoverability", "Structured entity data", parser.json_ld, "Add accurate Organisation or Service JSON-LD."),
        _finding("trust.heading", "Trust signals", "Primary heading", parser.h1, "Add one clear primary heading."),
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
    html = "<html><head><title>Demo</title><meta name='viewport' content='width=device-width'></head><body><h1>Demo</h1></body></html>"
    return Assessment.build("https://demo.veridra.local", analyze_document(html, {"x-content-type-options": "nosniff"}))
