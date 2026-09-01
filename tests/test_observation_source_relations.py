from __future__ import annotations

from veridra.collector import PageEvidence
from veridra.crawl import CrawledPage, CrawlResult
from veridra.observations import observation_records, page_observations


def _page(url: str, body: str) -> PageEvidence:
    return PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        body=body,
        redirect_chain=(),
        connected_ip="203.0.113.10",
        validated_ips=("203.0.113.10",),
    )


def test_page_observations_capture_only_proven_assessed_source_links() -> None:
    home = CrawledPage(
        _page(
            "https://example.com/",
            (
                '<a href="/about?utm=nav#team">About</a>'
                '<a href="/about#contact">About again</a>'
                '<a href="https://other.test/">External</a>'
            ),
        ),
        depth=0,
    )
    about = CrawledPage(
        _page("https://example.com/about", "<h1>About</h1>"),
        depth=1,
    )
    result = CrawlResult(
        pages=(about, home),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )

    pages = {item.url: item for item in page_observations(result)}

    assert pages["https://example.com/"].source_page_urls == ()
    assert pages["https://example.com/about"].source_page_urls == (
        "https://example.com/",
    )

    records = observation_records(tuple(pages.values()))
    source_record = next(
        item
        for item in records
        if item.subject == "https://example.com/about"
        and item.key == "page.source-pages"
    )
    assert source_record.state == '["https://example.com/"]'


def test_unassessed_links_are_not_promoted_to_source_page_relations() -> None:
    result = CrawlResult(
        pages=(
            CrawledPage(
                _page(
                    "https://example.com/",
                    '<a href="/not-assessed">Not assessed</a>',
                ),
                depth=0,
            ),
        ),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )

    page = page_observations(result)[0]

    assert page.source_page_urls == ()
