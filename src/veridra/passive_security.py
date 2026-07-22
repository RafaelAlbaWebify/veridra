from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .core import Finding, Status
from .crawl import CrawlResult

_MAX_EXAMPLES = 20


@dataclass
class _Signals:
    cross_origin_forms: list[str] = field(default_factory=list)
    insecure_forms: list[str] = field(default_factory=list)
    unsafe_blank_links: int = 0
    insecure_resources: list[str] = field(default_factory=list)


class _SecurityParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__()
        self.page_url = page_url
        self.signals = _Signals()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        lowered = tag.lower()
        if lowered == "form" and data.get("action", "").strip():
            action = urljoin(self.page_url, data["action"].strip())
            page = urlparse(self.page_url)
            parsed = urlparse(action)
            if parsed.scheme == "http":
                self.signals.insecure_forms.append(action)
            if parsed.hostname and parsed.hostname.lower() != (page.hostname or "").lower():
                self.signals.cross_origin_forms.append(action)
        if lowered == "a" and data.get("target", "").lower() == "_blank":
            rel = {item.lower() for item in data.get("rel", "").split()}
            if not ({"noopener", "noreferrer"} & rel):
                self.signals.unsafe_blank_links += 1
        for attribute in ("src", "href"):
            value = data.get(attribute, "").strip()
            if value.startswith("http://"):
                self.signals.insecure_resources.append(value)


def _finding(
    identifier: str,
    title: str,
    summary: str,
    recommendation: str,
    affected: list[dict[str, object]],
    *,
    severity: str = "medium",
) -> Finding:
    return Finding(
        id=identifier,
        area="Security posture",
        title=title,
        status=Status.attention if affected else Status.passed,
        severity=severity if affected else "info",
        summary=summary.format(count=len(affected)),
        recommendation=recommendation if affected else None,
        evidence={
            "affected_pages": affected[:_MAX_EXAMPLES],
            "bounded_examples": _MAX_EXAMPLES,
        },
    )


def analyze_passive_security(result: CrawlResult) -> list[Finding]:
    cookies: list[dict[str, object]] = []
    cross_origin_forms: list[dict[str, object]] = []
    insecure_forms: list[dict[str, object]] = []
    blank_links: list[dict[str, object]] = []
    insecure_resources: list[dict[str, object]] = []
    disclosures: list[dict[str, object]] = []
    unsafe_csp: list[dict[str, object]] = []

    for crawled in result.pages:
        page = crawled.evidence
        parser = _SecurityParser(page.final_url)
        parser.feed(page.body)
        parser.close()
        headers = {key.lower(): value for key, value in page.headers.items()}
        cookie = headers.get("set-cookie", "")
        if cookie:
            lowered_cookie = cookie.lower()
            missing = [
                name
                for name, token in (
                    ("Secure", "secure"),
                    ("HttpOnly", "httponly"),
                    ("SameSite", "samesite="),
                )
                if token not in lowered_cookie
            ]
            if missing:
                cookies.append({"url": page.final_url, "missing_flags": missing})
        if parser.signals.cross_origin_forms:
            cross_origin_forms.append(
                {"url": page.final_url, "actions": parser.signals.cross_origin_forms[:5]}
            )
        if parser.signals.insecure_forms:
            insecure_forms.append(
                {"url": page.final_url, "actions": parser.signals.insecure_forms[:5]}
            )
        if parser.signals.unsafe_blank_links:
            blank_links.append(
                {"url": page.final_url, "count": parser.signals.unsafe_blank_links}
            )
        if parser.signals.insecure_resources:
            insecure_resources.append(
                {"url": page.final_url, "resources": parser.signals.insecure_resources[:5]}
            )
        exposed = {
            name: headers[name]
            for name in ("server", "x-powered-by")
            if headers.get(name, "").strip()
        }
        if exposed:
            disclosures.append({"url": page.final_url, "headers": exposed})
        csp = headers.get("content-security-policy", "").lower()
        unsafe_tokens = [
            token
            for token in ("'unsafe-inline'", "'unsafe-eval'")
            if token in csp
        ]
        if unsafe_tokens:
            unsafe_csp.append({"url": page.final_url, "tokens": unsafe_tokens})

    return [
        _finding(
            "security.cookie-flags",
            "Cookie security attributes",
            (
                "{count} crawled pages set cookies without all detected Secure, "
                "HttpOnly and SameSite attributes."
            ),
            "Review each cookie and apply appropriate Secure, HttpOnly and SameSite attributes.",
            cookies,
            severity="high",
        ),
        _finding(
            "security.cross-origin-forms",
            "Cross-origin form submissions",
            "{count} crawled pages submit forms to a different hostname.",
            "Verify each cross-origin form destination, ownership and data-handling purpose.",
            cross_origin_forms,
            severity="high",
        ),
        _finding(
            "security.insecure-form-actions",
            "Insecure form actions",
            "{count} crawled pages expose an HTTP form action.",
            "Submit sensitive and personal data only to validated HTTPS endpoints.",
            insecure_forms,
            severity="high",
        ),
        _finding(
            "security.target-blank-isolation",
            "New-tab link isolation",
            (
                "{count} crawled pages contain target=_blank links without detectable "
                "noopener or noreferrer protection."
            ),
            "Add rel=noopener or rel=noreferrer to links that open a new browsing context.",
            blank_links,
            severity="low",
        ),
        _finding(
            "security.insecure-resources",
            "Insecure absolute resources",
            "{count} crawled pages reference absolute HTTP resources.",
            "Move public resources and links to validated HTTPS endpoints where supported.",
            insecure_resources,
            severity="high",
        ),
        _finding(
            "security.server-disclosure",
            "Server technology disclosure",
            "{count} crawled pages expose Server or X-Powered-By response values.",
            "Reduce unnecessary implementation-detail disclosure at the public edge.",
            disclosures,
            severity="low",
        ),
        _finding(
            "security.csp-unsafe-directives",
            "Content Security Policy unsafe directives",
            "{count} crawled pages expose a CSP containing unsafe-inline or unsafe-eval.",
            (
                "Review whether unsafe CSP directives can be replaced with nonces, "
                "hashes or narrower policies."
            ),
            unsafe_csp,
        ),
    ]
