from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree

from .collector import CollectionError, PageEvidence, collect_page
from .core import Finding, Status, UnsafeTargetError


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


@dataclass(frozen=True)
class BrokenInternalLink:
    target_url: str
    source_urls: tuple[str, ...]
    status_code: int | None
    collection_failed: bool


@dataclass(frozen=True)
class CrawlResult:
    pages: tuple[CrawledPage, ...]
    skipped_urls: tuple[str, ...]
    exhausted_page_limit: bool
    exhausted_byte_limit: bool
    sitemap_urls: tuple[str, ...] = ()
    sitemap_failures: tuple[str, ...] = ()
    broken_internal_links: tuple[BrokenInternalLink, ...] = ()


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
        if element.tag.rsplit("}", 1)[-1].lower() == "loc" and (element.text or "").strip()
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


def crawl_site(
    start_url: str,
    *,
    limits: CrawlLimits | None = None,
    collector: PageCollector = collect_page,
    robots_text: str = "",
) -> CrawlResult:
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
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    queue.extend((url, 0) for url in sitemap_urls)
    seen: set[str] = set()
    pages: list[CrawledPage] = []
    skipped: set[str] = set()
    total_bytes = 0
    byte_limit = False
    link_sources: defaultdict[str, set[str]] = defaultdict(set)
    broken: dict[str, BrokenInternalLink] = {}

    while queue and len(pages) < active_limits.max_pages:
        raw_url, depth = queue.popleft()
        normalized = _crawl_url(raw_url, start_url)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        try:
            page = collector(
                normalized,
                timeout=active_limits.timeout,
                max_bytes=active_limits.per_page_bytes,
            )
        except (CollectionError, UnsafeTargetError):
            skipped.add(normalized)
            if normalized in link_sources:
                broken[normalized] = BrokenInternalLink(
                    normalized,
                    tuple(sorted(link_sources[normalized])),
                    None,
                    True,
                )
            continue
        content_type = page.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            skipped.add(page.final_url)
            continue
        body_bytes = len(page.body.encode("utf-8"))
        if total_bytes + body_bytes > active_limits.max_total_bytes:
            byte_limit = True
            break
        total_bytes += body_bytes
        pages.append(CrawledPage(page, depth))
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
                if candidate not in seen:
                    queue.append((candidate, depth + 1))

    return CrawlResult(
        pages=tuple(pages),
        skipped_urls=tuple(sorted(skipped)),
        exhausted_page_limit=(bool(queue) and len(pages) >= active_limits.max_pages),
        exhausted_byte_limit=byte_limit,
        sitemap_urls=tuple(sitemap_urls),
        sitemap_failures=tuple(sitemap_failures),
        broken_internal_links=tuple(broken[url] for url in sorted(broken)),
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
    common_evidence = {
        "crawled_pages": len(result.pages),
        "skipped_urls": list(result.skipped_urls),
        "page_limit_reached": result.exhausted_page_limit,
        "byte_limit_reached": result.exhausted_byte_limit,
        "sitemap_urls": list(result.sitemap_urls),
        "sitemap_failures": list(result.sitemap_failures),
    }
    for identifier, (title, severity, affected) in checks.items():
        passed = not affected
        findings.append(
            Finding(
                id=identifier,
                area="Website health" if identifier in website_health_ids else "Search visibility",
                title=f"Multi-page {title.lower()}",
                status=Status.passed if passed else Status.attention,
                severity="info" if passed else severity,
                summary=(
                    f"All {len(result.pages)} crawled HTML pages passed this check."
                    if passed
                    else f"{len(affected)} of {len(result.pages)} crawled HTML pages need attention."
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
                else f"{len(broken)} internal link targets failed or returned an error response."
            ),
            recommendation=(
                None
                if not broken
                else "Correct or remove links to failed internal targets and verify their responses."
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
    return findings
