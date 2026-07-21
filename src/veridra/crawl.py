from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse

from .collector import CollectionError, PageEvidence, collect_page
from .core import Finding, Status, UnsafeTargetError


@dataclass(frozen=True)
class CrawlLimits:
    max_pages: int = 10
    max_depth: int = 1
    max_total_bytes: int = 5_000_000
    per_page_bytes: int = 750_000
    timeout: float = 8.0


@dataclass(frozen=True)
class CrawledPage:
    evidence: PageEvidence
    depth: int


@dataclass(frozen=True)
class CrawlResult:
    pages: tuple[CrawledPage, ...]
    skipped_urls: tuple[str, ...]
    exhausted_page_limit: bool
    exhausted_byte_limit: bool


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


def crawl_site(
    start_url: str,
    *,
    limits: CrawlLimits = CrawlLimits(),
    collector: PageCollector = collect_page,
) -> CrawlResult:
    if limits.max_pages < 1 or limits.max_depth < 0:
        raise ValueError(
            "Crawl limits must allow at least one page and non-negative depth."
        )
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    seen: set[str] = set()
    pages: list[CrawledPage] = []
    skipped: set[str] = set()
    total_bytes = 0
    byte_limit = False

    while queue and len(pages) < limits.max_pages:
        raw_url, depth = queue.popleft()
        normalized = _crawl_url(raw_url, start_url)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        try:
            page = collector(
                normalized,
                timeout=limits.timeout,
                max_bytes=limits.per_page_bytes,
            )
        except (CollectionError, UnsafeTargetError):
            skipped.add(normalized)
            continue
        content_type = page.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            skipped.add(page.final_url)
            continue
        body_bytes = len(page.body.encode("utf-8"))
        if total_bytes + body_bytes > limits.max_total_bytes:
            byte_limit = True
            break
        total_bytes += body_bytes
        pages.append(CrawledPage(page, depth))
        if depth >= limits.max_depth:
            continue
        parser = _PageSignals()
        parser.feed(page.body)
        for link in parser.links:
            candidate = _crawl_url(link, page.final_url)
            if candidate is not None and candidate not in seen:
                queue.append((candidate, depth + 1))

    return CrawlResult(
        pages=tuple(pages),
        skipped_urls=tuple(sorted(skipped)),
        exhausted_page_limit=bool(queue) and len(pages) >= limits.max_pages,
        exhausted_byte_limit=byte_limit,
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
    website_health_ids = {
        "crawl.http-status",
        "crawl.title",
        "crawl.h1",
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
                    else (
                        "Review and correct the affected pages for "
                        f"{title.lower()}."
                    )
                ),
                evidence={
                    "affected_urls": sorted(affected),
                    "crawled_pages": len(result.pages),
                    "skipped_urls": list(result.skipped_urls),
                    "page_limit_reached": result.exhausted_page_limit,
                    "byte_limit_reached": result.exhausted_byte_limit,
                },
            )
        )
    return findings
