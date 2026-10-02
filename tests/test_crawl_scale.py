from __future__ import annotations

from collections.abc import Callable

from veridra.collector import PageEvidence
from veridra.crawl import CrawlLimits, crawl_site


def _page(
    url: str,
    body: str,
    *,
    content_type: str = "text/html",
) -> PageEvidence:
    return PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": content_type},
        body=body,
        redirect_chain=(),
        connected_ip="93.184.216.34",
        validated_ips=("93.184.216.34",),
    )


def _five_hundred_page_collector(
    calls: list[str],
) -> Callable[..., PageEvidence]:
    sitemap_urls = ["https://example.com/"] + [
        f"https://example.com/page-{index}"
        for index in range(1, 500)
    ]
    sitemap = (
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join(f"<url><loc>{url}</loc></url>" for url in sitemap_urls)
        + "</urlset>"
    )

    def collect(url: str, **_: object) -> PageEvidence:
        calls.append(url)
        if url == "https://example.com/sitemap.xml":
            return _page(
                url,
                sitemap,
                content_type="application/xml",
            )
        if url == "https://example.com/" or url.startswith(
            "https://example.com/page-"
        ):
            return _page(
                url,
                "<html><head><title>Scale fixture</title>"
                "<meta name='description' content='Scale fixture'>"
                "<link rel='canonical' href='" + url + "'></head>"
                "<body><h1>Scale fixture</h1></body></html>",
            )
        raise AssertionError(f"Unexpected scale-fixture URL: {url}")

    return collect


def test_bounded_crawler_processes_measured_500_page_sitemap_workload() -> None:
    calls: list[str] = []
    progress: list[int] = []

    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(
            max_pages=500,
            max_depth=0,
            max_total_bytes=20_000_000,
            per_page_bytes=250_000,
            timeout=2.0,
            max_sitemaps=1,
            max_sitemap_urls=500,
        ),
        collector=_five_hundred_page_collector(calls),
        progress_callback=progress.append,
    )

    assert len(result.pages) == 500
    assert result.summary.attempted_pages == 500
    assert result.summary.successful_pages == 500
    assert result.summary.failed_pages == 0
    assert result.summary.blocked_pages == 0
    assert result.summary.skipped_pages == 0
    assert result.exhausted_page_limit is False
    assert result.exhausted_byte_limit is False
    assert result.sitemap_urls[0] == "https://example.com/"
    assert len(result.sitemap_urls) == 500
    assert progress[0] == 1
    assert progress[-1] == 500
    assert len(progress) == 500
    assert len(calls) == 501  # sitemap + 500 HTML pages
    assert result.summary.duration_seconds >= 0.0
