from __future__ import annotations

import heapq
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from html.parser import HTMLParser
from time import perf_counter
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree

from .collector import CollectionError, PageEvidence, collect_page
from .core import Finding, Status, UnsafeTargetError
from .robots import robots_allows_url


@dataclass(frozen=True)
class CrawlLimits:
    max_pages: int = 10
    max_depth: int = 1
    max_total_bytes: int = 5_000_000
    per_page_bytes: int = 750_000
    timeout: float = 8.0
    max_sitemaps: int = 5
    max_sitemap_urls: int = 100


@dataclass(frozen=True)
class CrawledPage:
    evidence: PageEvidence
    depth: int
    fetch_mode: str = "STATIC_STANDARD"


@dataclass(frozen=True)
class BrokenInternalLink:
    target_url: str
    source_urls: tuple[str, ...]
    status_code: int | None
    collection_failed: bool


class FetchMode(StrEnum):
    static_standard = "STATIC_STANDARD"
    blocked = "BLOCKED"
    failed = "FAILED"


@dataclass(frozen=True)
class CrawlAttempt:
    requested_url: str
    final_url: str | None
    depth: int
    fetch_mode: FetchMode
    status_code: int | None = None
    response_bytes: int = 0
    included_html: bool = False
    reason: str | None = None
    selection_reason: str | None = None
    selection_priority: int | None = None


@dataclass(frozen=True)
class CrawlSummary:
    attempted_pages: int = 0
    successful_pages: int = 0
    blocked_pages: int = 0
    failed_pages: int = 0
    skipped_pages: int = 0
    total_downloaded_bytes: int = 0
    status_counts: dict[int, int] = field(default_factory=dict)
    fetch_mode_counts: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def evidence(self) -> dict[str, object]:
        return {
            "attempted_pages": self.attempted_pages,
            "successful_pages": self.successful_pages,
            "blocked_pages": self.blocked_pages,
            "failed_pages": self.failed_pages,
            "skipped_pages": self.skipped_pages,
            "total_downloaded_bytes": self.total_downloaded_bytes,
            "status_counts": self.status_counts,
            "fetch_mode_counts": self.fetch_mode_counts,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class CrawlResult:
    pages: tuple[CrawledPage, ...]
    skipped_urls: tuple[str, ...]
    exhausted_page_limit: bool
    exhausted_byte_limit: bool
    sitemap_urls: tuple[str, ...] = ()
    sitemap_failures: tuple[str, ...] = ()
    broken_internal_links: tuple[BrokenInternalLink, ...] = ()
    attempts: tuple[CrawlAttempt, ...] = ()
    blocked_urls: tuple[str, ...] = ()
    failed_urls: tuple[str, ...] = ()
    summary: CrawlSummary = field(default_factory=CrawlSummary)


PageCollector = Callable[..., PageEvidence]


class _PageSignals(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.has_title = False
        self.has_description = False
        self.has_h1 = False
        self.has_canonical = False
        self.has_mixed_content = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        lowered = {key: value.lower() for key, value in data.items()}
        if tag == "title":
            self.has_title = True
        if tag == "h1":
            self.has_h1 = True
        if tag == "meta" and lowered.get("name") == "description":
            self.has_description = bool(data.get("content", "").strip())
        if tag == "link" and "canonical" in lowered.get("rel", ""):
            self.has_canonical = bool(data.get("href", "").strip())
        if tag == "a" and data.get("href"):
            self.links.append(data["href"])
        if any(
            lowered.get(name, "").startswith("http://")
            for name in ("src", "href")
        ):
            self.has_mixed_content = True


_STATIC_SUFFIXES = {
    ".avif",
    ".css",
    ".eot",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".svg",
    ".ttf",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xml",
    ".zip",
}
_OWNER_ROUTE_TERMS = (
    "contact",
    "contact-us",
    "about",
    "about-us",
    "opening-hours",
    "openinghours",
    "hours",
    "location",
    "locations",
    "find-us",
    "directions",
    "services",
    "service",
    "treatments",
    "treatment",
    "fees",
    "pricing",
    "prices",
    "price",
    "booking",
    "book",
    "appointment",
    "appointments",
    "sample-page",
)
_TRUST_ROUTE_TERMS = (
    "privacy",
    "terms",
    "cookies",
    "data-protection",
)
_LOW_VALUE_ROUTE_TERMS = (
    "blog",
    "news",
    "article",
    "articles",
    "resource",
    "resources",
    "category",
    "tag",
    "author",
    "wp-content",
    "wp-json",
    "feed",
)


@dataclass(order=True, frozen=True)
class _QueuedUrl:
    priority: int
    sequence: int
    url: str = field(compare=False)
    depth: int = field(compare=False)
    reason: str = field(compare=False)


def _crawl_url(raw: str, base_url: str) -> str | None:
    joined = urljoin(base_url, raw)
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    base = urlparse(base_url)
    if parsed.hostname.lower() != (base.hostname or "").lower():
        return None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    base_port = base.port or (443 if base.scheme == "https" else 80)
    if port != base_port:
        return None
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _looks_like_static_asset(url: str) -> bool:
    path = urlparse(url).path.casefold().rstrip("/")
    return any(path.endswith(suffix) for suffix in _STATIC_SUFFIXES)


def _route_priority(url: str, *, source: str) -> tuple[int, str]:
    path = urlparse(url).path.casefold()
    segments = tuple(part for part in path.split("/") if part)
    if path in {"", "/"}:
        return 0, "homepage"
    if any(term in segments or term in path for term in _OWNER_ROUTE_TERMS):
        return 10, f"{source}:owner-facing-route"
    if any(term in segments or term in path for term in _TRUST_ROUTE_TERMS):
        return 20, f"{source}:trust-route"
    if any(term in segments or term in path for term in _LOW_VALUE_ROUTE_TERMS):
        return 50, f"{source}:low-value-route"
    return 30, f"{source}:generic-route"


def _robots_sitemaps(robots_text: str, start_url: str) -> list[str]:
    values: list[str] = []
    for line in robots_text.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("sitemap:"):
            continue
        candidate = _crawl_url(stripped.split(":", 1)[1].strip(), start_url)
        if candidate is not None:
            values.append(candidate)
    conventional = _crawl_url("/sitemap.xml", start_url)
    if conventional is not None:
        values.append(conventional)
    return list(dict.fromkeys(values))


def _xml_locations(body: str) -> tuple[str, list[str]]:
    root = ElementTree.fromstring(body)
    kind = root.tag.rsplit("}", 1)[-1].lower()
    locations = [
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() == "loc"
        and (element.text or "").strip()
    ]
    return kind, locations


def _discover_sitemap_urls(
    start_url: str,
    robots_text: str,
    limits: CrawlLimits,
    collector: PageCollector,
) -> tuple[list[str], list[str]]:
    pending = deque(_robots_sitemaps(robots_text, start_url))
    seen_sitemaps: set[str] = set()
    discovered: list[str] = []
    failures: set[str] = set()

    while pending and len(seen_sitemaps) < limits.max_sitemaps:
        sitemap_url = pending.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            page = collector(
                sitemap_url,
                timeout=limits.timeout,
                max_bytes=limits.per_page_bytes,
            )
            if not 200 <= page.status_code < 400:
                failures.add(sitemap_url)
                continue
            kind, locations = _xml_locations(page.body)
        except (CollectionError, UnsafeTargetError, ElementTree.ParseError):
            failures.add(sitemap_url)
            continue

        for raw_location in locations:
            candidate = _crawl_url(raw_location, start_url)
            if candidate is None:
                continue
            if kind == "sitemapindex":
                if candidate not in seen_sitemaps:
                    pending.append(candidate)
            elif kind == "urlset" and candidate not in discovered:
                discovered.append(candidate)
                if len(discovered) >= limits.max_sitemap_urls:
                    return discovered, sorted(failures)
        if kind not in {"sitemapindex", "urlset"}:
            failures.add(sitemap_url)

    return discovered, sorted(failures)


def _blocked_status(status_code: int) -> bool:
    return status_code in {401, 403, 429}


def _build_summary(
    attempts: list[CrawlAttempt],
    duration_seconds: float,
) -> CrawlSummary:
    status_counts = Counter(
        attempt.status_code
        for attempt in attempts
        if attempt.status_code is not None
    )
    mode_counts = Counter(attempt.fetch_mode.value for attempt in attempts)
    return CrawlSummary(
        attempted_pages=len(attempts),
        successful_pages=sum(
            1
            for attempt in attempts
            if attempt.included_html
            and attempt.status_code is not None
            and 200 <= attempt.status_code < 400
        ),
        blocked_pages=sum(
            1 for attempt in attempts if attempt.fetch_mode is FetchMode.blocked
        ),
        failed_pages=sum(
            1 for attempt in attempts if attempt.fetch_mode is FetchMode.failed
        ),
        skipped_pages=sum(
            1
            for attempt in attempts
            if attempt.fetch_mode is FetchMode.static_standard
            and not attempt.included_html
        ),
        total_downloaded_bytes=sum(attempt.response_bytes for attempt in attempts),
        status_counts=dict(sorted(status_counts.items())),
        fetch_mode_counts=dict(sorted(mode_counts.items())),
        duration_seconds=round(max(0.0, duration_seconds), 3),
    )


def crawl_site(
    start_url: str,
    *,
    limits: CrawlLimits | None = None,
    collector: PageCollector = collect_page,
    robots_text: str = "",
) -> CrawlResult:
    started = perf_counter()
    active_limits = limits or CrawlLimits()
    if (
        active_limits.max_pages < 1
        or active_limits.max_depth < 0
        or active_limits.max_sitemaps < 0
        or active_limits.max_sitemap_urls < 0
    ):
        raise ValueError("Crawl limits must be non-negative and allow at least one page.")

    sitemap_urls, sitemap_failures = _discover_sitemap_urls(
        start_url,
        robots_text,
        active_limits,
        collector,
    )
    queue: list[_QueuedUrl] = []
    queued: set[str] = set()
    seen: set[str] = set()
    sequence = 0

    def enqueue(url: str, depth: int, *, source: str) -> None:
        nonlocal sequence
        normalized = _crawl_url(url, start_url)
        if normalized is None or normalized in seen or normalized in queued:
            return
        if _looks_like_static_asset(normalized):
            return
        priority, reason = _route_priority(normalized, source=source)
        heapq.heappush(
            queue,
            _QueuedUrl(priority, sequence, normalized, depth, reason),
        )
        queued.add(normalized)
        sequence += 1

    enqueue(start_url, 0, source="start")
    for url in sitemap_urls:
        enqueue(url, 0, source="sitemap")

    pages: list[CrawledPage] = []
    skipped: set[str] = set()
    blocked_urls: set[str] = set()
    failed_urls: set[str] = set()
    attempts: list[CrawlAttempt] = []
    total_bytes = 0
    byte_limit = False
    link_sources: defaultdict[str, set[str]] = defaultdict(set)
    broken: dict[str, BrokenInternalLink] = {}

    while queue and len(pages) < active_limits.max_pages:
        selected = heapq.heappop(queue)
        queued.discard(selected.url)
        normalized = selected.url
        depth = selected.depth
        if normalized in seen:
            continue
        seen.add(normalized)

        if not robots_allows_url(robots_text, "Veridra", normalized):
            blocked_urls.add(normalized)
            attempts.append(
                CrawlAttempt(
                    requested_url=normalized,
                    final_url=None,
                    depth=depth,
                    fetch_mode=FetchMode.blocked,
                    reason="robots.txt disallows this URL for the Veridra crawler",
                    selection_reason=selected.reason,
                    selection_priority=selected.priority,
                )
            )
            continue

        try:
            page = collector(
                normalized,
                timeout=active_limits.timeout,
                max_bytes=active_limits.per_page_bytes,
            )
        except (CollectionError, UnsafeTargetError) as exc:
            failed_urls.add(normalized)
            attempts.append(
                CrawlAttempt(
                    requested_url=normalized,
                    final_url=None,
                    depth=depth,
                    fetch_mode=FetchMode.failed,
                    reason=str(exc),
                    selection_reason=selected.reason,
                    selection_priority=selected.priority,
                )
            )
            continue

        body_bytes = len(page.body.encode("utf-8"))
        if _blocked_status(page.status_code):
            blocked_urls.add(page.final_url)
            attempts.append(
                CrawlAttempt(
                    requested_url=normalized,
                    final_url=page.final_url,
                    depth=depth,
                    fetch_mode=FetchMode.blocked,
                    status_code=page.status_code,
                    response_bytes=body_bytes,
                    reason=f"HTTP {page.status_code} prevented normal assessment retrieval",
                    selection_reason=selected.reason,
                    selection_priority=selected.priority,
                )
            )
            continue

        content_type = page.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            skipped.add(page.final_url)
            attempts.append(
                CrawlAttempt(
                    requested_url=normalized,
                    final_url=page.final_url,
                    depth=depth,
                    fetch_mode=FetchMode.static_standard,
                    status_code=page.status_code,
                    response_bytes=body_bytes,
                    reason="non-HTML response",
                    selection_reason=selected.reason,
                    selection_priority=selected.priority,
                )
            )
            continue

        if total_bytes + body_bytes > active_limits.max_total_bytes:
            byte_limit = True
            skipped.add(page.final_url)
            attempts.append(
                CrawlAttempt(
                    requested_url=normalized,
                    final_url=page.final_url,
                    depth=depth,
                    fetch_mode=FetchMode.static_standard,
                    status_code=page.status_code,
                    response_bytes=body_bytes,
                    reason="crawl total-byte limit reached before including this page",
                    selection_reason=selected.reason,
                    selection_priority=selected.priority,
                )
            )
            break

        total_bytes += body_bytes
        attempts.append(
            CrawlAttempt(
                requested_url=normalized,
                final_url=page.final_url,
                depth=depth,
                fetch_mode=FetchMode.static_standard,
                status_code=page.status_code,
                response_bytes=body_bytes,
                included_html=True,
                selection_reason=selected.reason,
                selection_priority=selected.priority,
            )
        )
        pages.append(CrawledPage(page, depth, FetchMode.static_standard.value))

        if page.status_code >= 400 and normalized in link_sources:
            broken[normalized] = BrokenInternalLink(
                normalized,
                tuple(sorted(link_sources[normalized])),
                page.status_code,
                False,
            )
        if depth >= active_limits.max_depth:
            continue
        parser = _PageSignals()
        parser.feed(page.body)
        for link in parser.links:
            candidate = _crawl_url(link, page.final_url)
            if candidate is not None:
                link_sources[candidate].add(page.final_url)
                enqueue(candidate, depth + 1, source="page-link")

    summary = _build_summary(attempts, perf_counter() - started)
    return CrawlResult(
        pages=tuple(pages),
        skipped_urls=tuple(sorted(skipped)),
        exhausted_page_limit=(bool(queue) and len(pages) >= active_limits.max_pages),
        exhausted_byte_limit=byte_limit,
        sitemap_urls=tuple(sitemap_urls),
        sitemap_failures=tuple(sitemap_failures),
        broken_internal_links=tuple(broken[url] for url in sorted(broken)),
        attempts=tuple(attempts),
        blocked_urls=tuple(sorted(blocked_urls)),
        failed_urls=tuple(sorted(failed_urls)),
        summary=summary,
    )


def analyze_crawl(result: CrawlResult) -> list[Finding]:
    checks: dict[str, tuple[str, str, list[str]]] = {
        "crawl.http-status": ("Page response", "high", []),
        "crawl.title": ("Document title", "medium", []),
        "crawl.description": ("Meta description", "medium", []),
        "crawl.h1": ("Primary heading", "medium", []),
        "crawl.canonical": ("Canonical URL", "medium", []),
        "crawl.mixed-content": ("No obvious mixed content", "high", []),
    }
    for crawled in result.pages:
        page = crawled.evidence
        parser = _PageSignals()
        parser.feed(page.body)
        if not 200 <= page.status_code < 400:
            checks["crawl.http-status"][2].append(page.final_url)
        if not parser.has_title:
            checks["crawl.title"][2].append(page.final_url)
        if not parser.has_description:
            checks["crawl.description"][2].append(page.final_url)
        if not parser.has_h1:
            checks["crawl.h1"][2].append(page.final_url)
        if not parser.has_canonical:
            checks["crawl.canonical"][2].append(page.final_url)
        if parser.has_mixed_content:
            checks["crawl.mixed-content"][2].append(page.final_url)

    findings: list[Finding] = []
    website_health_ids = {"crawl.http-status", "crawl.title", "crawl.h1"}
    selection_evidence = [
        {
            "requested_url": attempt.requested_url,
            "included_html": attempt.included_html,
            "selection_reason": attempt.selection_reason,
            "selection_priority": attempt.selection_priority,
        }
        for attempt in result.attempts
    ]
    common_evidence = {
        "crawled_pages": len(result.pages),
        "skipped_urls": list(result.skipped_urls),
        "blocked_urls": list(result.blocked_urls),
        "failed_urls": list(result.failed_urls),
        "page_limit_reached": result.exhausted_page_limit,
        "byte_limit_reached": result.exhausted_byte_limit,
        "sitemap_urls": list(result.sitemap_urls),
        "sitemap_failures": list(result.sitemap_failures),
        "crawl_summary": result.summary.evidence(),
        "fetch_mode": FetchMode.static_standard.value,
        "selection_evidence": selection_evidence,
    }
    for identifier, (title, severity, affected) in checks.items():
        passed = not affected
        findings.append(
            Finding(
                id=identifier,
                area=(
                    "Website health"
                    if identifier in website_health_ids
                    else "Search visibility"
                ),
                title=f"Multi-page {title.lower()}",
                status=Status.passed if passed else Status.attention,
                severity="info" if passed else severity,
                summary=(
                    f"All {len(result.pages)} crawled HTML pages passed this check."
                    if passed
                    else (
                        f"{len(affected)} of {len(result.pages)} crawled HTML "
                        "pages need attention."
                    )
                ),
                recommendation=(
                    None
                    if passed
                    else f"Review and correct the affected pages for {title.lower()}."
                ),
                evidence={"affected_urls": sorted(affected), **common_evidence},
            )
        )

    broken = result.broken_internal_links
    findings.append(
        Finding(
            id="crawl.broken-internal-links",
            area="Website health",
            title="Broken internal links",
            status=Status.passed if not broken else Status.attention,
            severity="info" if not broken else "high",
            summary=(
                "No broken internal links were observed in the bounded crawl."
                if not broken
                else f"{len(broken)} internal link targets returned an error response."
            ),
            recommendation=(
                None
                if not broken
                else (
                    "Correct or remove links to failed internal targets and verify "
                    "their responses."
                )
            ),
            evidence={
                "broken_targets": [
                    {
                        "target_url": item.target_url,
                        "source_urls": list(item.source_urls),
                        "status_code": item.status_code,
                        "collection_failed": item.collection_failed,
                    }
                    for item in broken
                ],
                **common_evidence,
            },
        )
    )

    incomplete = bool(
        result.blocked_urls
        or result.failed_urls
        or result.exhausted_page_limit
        or result.exhausted_byte_limit
    )
    findings.append(
        Finding(
            id="crawl.retrieval-coverage",
            area="Website health",
            title="Crawl retrieval coverage",
            status=Status.unavailable if incomplete else Status.passed,
            severity="info",
            summary=(
                (
                    f"{len(result.pages)} HTML pages were analyzed, with "
                    f"{len(result.blocked_urls)} blocked and "
                    f"{len(result.failed_urls)} failed retrievals."
                )
                if incomplete
                else (
                    f"All {result.summary.attempted_pages} attempted crawl URLs were "
                    "retrieved within the configured assessment boundaries."
                )
            ),
            recommendation=(
                (
                    "Review blocked, failed or limit-truncated URLs before treating the "
                    "absence of findings as proof that those pages are healthy."
                )
                if incomplete
                else None
            ),
            evidence=common_evidence,
        )
    )
    return findings
