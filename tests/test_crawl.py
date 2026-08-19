from __future__ import annotations

from collections.abc import Callable

from veridra.collector import CollectionError, PageEvidence
from veridra.core import Status
from veridra.crawl import CrawlLimits, FetchMode, analyze_crawl, crawl_site


def _page(
    url: str,
    body: str,
    *,
    content_type: str = "text/html",
    status_code: int = 200,
) -> PageEvidence:
    return PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=status_code,
        headers={"content-type": content_type},
        body=body,
        redirect_chain=(),
        connected_ip="93.184.216.34",
        validated_ips=("93.184.216.34",),
    )


def _collector(
    pages: dict[str, PageEvidence],
    calls: list[str],
) -> Callable[..., PageEvidence]:
    def collect(url: str, **_: object) -> PageEvidence:
        calls.append(url)
        try:
            return pages[url]
        except KeyError as exc:
            raise CollectionError(f"Missing fixture: {url}") from exc

    return collect


def test_crawl_is_same_origin_sequential_and_bounded() -> None:
    pages = {
        "https://example.com/": _page(
            "https://example.com/",
            "<html><head><title>Home</title></head><body><h1>Home</h1>"
            "<a href='/about?utm_source=x#team'>About</a>"
            "<a href='https://other.example/path'>External</a></body></html>",
        ),
        "https://example.com/about": _page(
            "https://example.com/about",
            "<html><head><title>About</title></head><body><h1>About</h1>"
            "<a href='/deep'>Deep</a></body></html>",
        ),
    }
    calls: list[str] = []
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=2, max_depth=1, max_sitemaps=0),
        collector=_collector(pages, calls),
    )

    assert calls == ["https://example.com/", "https://example.com/about"]
    assert [page.evidence.final_url for page in result.pages] == calls
    assert result.exhausted_page_limit is False
    assert result.summary.attempted_pages == 2
    assert result.summary.successful_pages == 2
    assert result.summary.fetch_mode_counts == {FetchMode.static_standard.value: 2}


def test_crawl_reports_page_limit() -> None:
    pages = {
        "https://example.com/": _page(
            "https://example.com/", "<a href='/one'>One</a><a href='/two'>Two</a>"
        ),
        "https://example.com/one": _page("https://example.com/one", "<p>One</p>"),
    }
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=2, max_depth=1, max_sitemaps=0),
        collector=_collector(pages, []),
    )
    assert len(result.pages) == 2
    assert result.exhausted_page_limit is True


def test_crawl_respects_total_byte_limit() -> None:
    page = _page("https://example.com/", "x" * 20)
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_total_bytes=10, max_sitemaps=0),
        collector=_collector({"https://example.com/": page}, []),
    )
    assert result.pages == ()
    assert result.exhausted_byte_limit is True
    assert result.summary.attempted_pages == 1
    assert result.summary.total_downloaded_bytes == 20


def test_aggregate_findings_include_affected_urls() -> None:
    complete = (
        "<html><head><title>Good</title>"
        "<meta name='description' content='Good'>"
        "<link rel='canonical' href='https://example.com/'>"
        "</head><body><h1>Good</h1></body></html>"
    )
    incomplete = "<html><body><img src='http://example.com/image.png'></body></html>"
    pages = {
        "https://example.com/": _page(
            "https://example.com/", complete + "<a href='/bad'>Bad</a>"
        ),
        "https://example.com/bad": _page("https://example.com/bad", incomplete),
    }
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=2, max_depth=1, max_sitemaps=0),
        collector=_collector(pages, []),
    )
    findings = {finding.id: finding for finding in analyze_crawl(result)}

    assert findings["crawl.title"].status == Status.attention
    assert findings["crawl.title"].evidence["affected_urls"] == [
        "https://example.com/bad"
    ]
    assert findings["crawl.mixed-content"].status == Status.attention
    assert findings["crawl.http-status"].status == Status.passed
    assert findings["crawl.title"].evidence["fetch_mode"] == "STATIC_STANDARD"
    assert findings["crawl.title"].evidence["crawl_summary"]["successful_pages"] == 2


def test_non_html_pages_are_skipped_and_not_marked_broken() -> None:
    pages = {
        "https://example.com/": _page(
            "https://example.com/", "<a href='/file.pdf'>PDF</a>"
        ),
        "https://example.com/file.pdf": _page(
            "https://example.com/file.pdf",
            "%PDF",
            content_type="application/pdf",
        ),
    }
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=3, max_depth=1, max_sitemaps=0),
        collector=_collector(pages, []),
    )
    assert len(result.pages) == 1
    assert result.skipped_urls == ("https://example.com/file.pdf",)
    assert result.broken_internal_links == ()
    assert result.summary.skipped_pages == 1


def test_sitemap_index_and_urlset_add_same_origin_pages() -> None:
    pages = {
        "https://example.com/sitemap.xml": _page(
            "https://example.com/sitemap.xml",
            "<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
            "<sitemap><loc>https://example.com/pages.xml</loc></sitemap>"
            "<sitemap><loc>https://external.example/out.xml</loc></sitemap>"
            "</sitemapindex>",
            content_type="application/xml",
        ),
        "https://example.com/pages.xml": _page(
            "https://example.com/pages.xml",
            "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
            "<url><loc>https://example.com/</loc></url>"
            "<url><loc>https://example.com/from-map?x=1#part</loc></url>"
            "</urlset>",
            content_type="application/xml",
        ),
        "https://example.com/": _page("https://example.com/", "<h1>Home</h1>"),
        "https://example.com/from-map": _page(
            "https://example.com/from-map", "<h1>Mapped</h1>"
        ),
    }
    calls: list[str] = []
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=5, max_depth=0),
        collector=_collector(pages, calls),
        robots_text="Sitemap: https://example.com/sitemap.xml",
    )

    assert [page.evidence.final_url for page in result.pages] == [
        "https://example.com/",
        "https://example.com/from-map",
    ]
    assert result.sitemap_urls == (
        "https://example.com/",
        "https://example.com/from-map",
    )
    assert "https://external.example/out.xml" not in calls


def test_broken_internal_links_exclude_failed_retrievals() -> None:
    pages = {
        "https://example.com/": _page(
            "https://example.com/",
            "<a href='/missing'>Missing</a><a href='/failed'>Failed</a>",
        ),
        "https://example.com/missing": _page(
            "https://example.com/missing", "Not found", status_code=404
        ),
    }
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=4, max_depth=1, max_sitemaps=0),
        collector=_collector(pages, []),
    )
    findings = {finding.id: finding for finding in analyze_crawl(result)}
    broken = findings["crawl.broken-internal-links"]

    assert broken.status == Status.attention
    assert broken.evidence["broken_targets"] == [
        {
            "target_url": "https://example.com/missing",
            "source_urls": ["https://example.com/"],
            "status_code": 404,
            "collection_failed": False,
        }
    ]
    assert result.failed_urls == ("https://example.com/failed",)
    assert result.summary.failed_pages == 1


def test_blocked_http_response_is_not_analyzed_as_page_quality_failure() -> None:
    complete = (
        "<html><head><title>Home</title><meta name='description' content='Good'>"
        "<link rel='canonical' href='https://example.com/'></head>"
        "<body><h1>Home</h1><a href='/blocked'>Blocked</a></body></html>"
    )
    pages = {
        "https://example.com/": _page("https://example.com/", complete),
        "https://example.com/blocked": _page(
            "https://example.com/blocked",
            "Access denied",
            status_code=403,
        ),
    }
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=3, max_depth=1, max_sitemaps=0),
        collector=_collector(pages, []),
    )
    findings = {finding.id: finding for finding in analyze_crawl(result)}

    assert len(result.pages) == 1
    assert result.blocked_urls == ("https://example.com/blocked",)
    assert result.summary.blocked_pages == 1
    assert result.summary.status_counts[403] == 1
    assert findings["crawl.title"].status == Status.passed
    assert findings["crawl.h1"].status == Status.passed
    assert findings["crawl.retrieval-coverage"].status == Status.unavailable


def test_robots_disallowed_page_is_recorded_without_fetching_it() -> None:
    pages = {
        "https://example.com/": _page(
            "https://example.com/",
            "<a href='/public'>Public</a><a href='/private/secret'>Private</a>",
        ),
        "https://example.com/public": _page(
            "https://example.com/public", "<h1>Public</h1>"
        ),
    }
    calls: list[str] = []
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=5, max_depth=1, max_sitemaps=0),
        collector=_collector(pages, calls),
        robots_text="User-agent: *\nDisallow: /private/\n",
    )

    assert calls == ["https://example.com/", "https://example.com/public"]
    assert result.blocked_urls == ("https://example.com/private/secret",)
    assert result.summary.blocked_pages == 1
    blocked = [
        attempt
        for attempt in result.attempts
        if attempt.fetch_mode is FetchMode.blocked
    ]
    assert len(blocked) == 1
    assert blocked[0].status_code is None
    assert "robots.txt" in (blocked[0].reason or "")


def test_invalid_sitemap_is_recorded_without_crashing() -> None:
    pages = {
        "https://example.com/sitemap.xml": _page(
            "https://example.com/sitemap.xml",
            "not xml",
            content_type="application/xml",
        ),
        "https://example.com/": _page("https://example.com/", "<h1>Home</h1>"),
    }
    result = crawl_site(
        "https://example.com/",
        collector=_collector(pages, []),
    )
    assert result.sitemap_failures == ("https://example.com/sitemap.xml",)
    assert len(result.pages) == 1
