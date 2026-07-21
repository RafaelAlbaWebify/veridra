from __future__ import annotations

from collections.abc import Iterator

from veridra.collector import PageEvidence
from veridra.crawl import CrawlLimits, analyze_crawl, crawl_site
from veridra.core import Status


def _page(url: str, body: str, *, content_type: str = "text/html") -> PageEvidence:
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


def _collector(pages: dict[str, PageEvidence], calls: list[str]):
    def collect(url: str, **_: object) -> PageEvidence:
        calls.append(url)
        return pages[url]

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
        limits=CrawlLimits(max_pages=2, max_depth=1),
        collector=_collector(pages, calls),
    )

    assert calls == ["https://example.com/", "https://example.com/about"]
    assert [page.evidence.final_url for page in result.pages] == calls
    assert result.exhausted_page_limit is False


def test_crawl_reports_page_limit() -> None:
    pages = {
        "https://example.com/": _page(
            "https://example.com/",
            "<a href='/one'>One</a><a href='/two'>Two</a>",
        ),
        "https://example.com/one": _page("https://example.com/one", "<p>One</p>"),
    }
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=2, max_depth=1),
        collector=_collector(pages, []),
    )
    assert len(result.pages) == 2
    assert result.exhausted_page_limit is True


def test_crawl_respects_total_byte_limit() -> None:
    page = _page("https://example.com/", "x" * 20)
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_total_bytes=10),
        collector=_collector({"https://example.com/": page}, []),
    )
    assert result.pages == ()
    assert result.exhausted_byte_limit is True


def test_aggregate_findings_include_affected_urls() -> None:
    complete = "<html><head><title>Good</title><meta name='description' content='Good'><link rel='canonical' href='https://example.com/'></head><body><h1>Good</h1></body></html>"
    incomplete = "<html><body><img src='http://example.com/image.png'></body></html>"
    pages = {
        "https://example.com/": _page(
            "https://example.com/",
            complete + "<a href='/bad'>Bad</a>",
        ),
        "https://example.com/bad": _page("https://example.com/bad", incomplete),
    }
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=2, max_depth=1),
        collector=_collector(pages, []),
    )
    findings = {finding.id: finding for finding in analyze_crawl(result)}

    assert findings["crawl.title"].status == Status.attention
    assert findings["crawl.title"].evidence["affected_urls"] == [
        "https://example.com/bad"
    ]
    assert findings["crawl.mixed-content"].status == Status.attention
    assert findings["crawl.http-status"].status == Status.passed


def test_non_html_pages_are_skipped() -> None:
    pages = {
        "https://example.com/": _page(
            "https://example.com/",
            "<a href='/file.pdf'>PDF</a>",
        ),
        "https://example.com/file.pdf": _page(
            "https://example.com/file.pdf",
            "%PDF",
            content_type="application/pdf",
        ),
    }
    result = crawl_site(
        "https://example.com/",
        limits=CrawlLimits(max_pages=3, max_depth=1),
        collector=_collector(pages, []),
    )
    assert len(result.pages) == 1
    assert result.skipped_urls == ("https://example.com/file.pdf",)
