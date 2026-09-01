from __future__ import annotations

from veridra.collector import PageEvidence
from veridra.crawl import CrawledPage, CrawlResult
from veridra.observations import observation_records, page_observations


def _page(url: str, body: str, *, status: int = 200) -> PageEvidence:
    return PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=status,
        headers={"content-type": "text/html; charset=utf-8"},
        body=body,
        redirect_chain=(),
        connected_ip="203.0.113.10",
        validated_ips=("203.0.113.10",),
    )


def test_page_observation_normalizes_directly_observed_page_facts() -> None:
    result = CrawlResult(
        pages=(
            CrawledPage(
                _page(
                    "https://example.com/about",
                    """
                    <html><head>
                    <title> About   Us </title>
                    <meta name="description" content="Company profile">
                    <link rel="canonical" href="/about">
                    <script type="application/ld+json">
                    {"@graph":[{"@type":"Organization"},{"@type":["WebPage","AboutPage"]}]}
                    </script>
                    </head><body><h1>About Example</h1></body></html>
                    """,
                ),
                depth=1,
            ),
        ),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )

    pages = page_observations(result)

    assert len(pages) == 1
    page = pages[0]
    assert page.url == "https://example.com/about"
    assert page.status_code == 200
    assert page.depth == 1
    assert page.title == "About Us"
    assert page.meta_description == "Company profile"
    assert page.h1_count == 1
    assert page.h1_text == "About Example"
    assert page.canonical_url == "https://example.com/about"
    assert page.indexable is True
    assert page.structured_data_types == ("AboutPage", "Organization", "WebPage")
    assert len(page.fingerprint) == 64


def test_page_identity_and_fingerprint_are_deterministic_across_crawl_order() -> None:
    first_page = CrawledPage(
        _page("https://example.com/", "<html><title>Home</title><h1>Home</h1></html>"),
        depth=0,
    )
    second_page = CrawledPage(
        _page("https://example.com/contact", "<html><title>Contact</title></html>"),
        depth=1,
    )
    first = CrawlResult(
        pages=(second_page, first_page),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )
    second = CrawlResult(
        pages=(first_page, second_page),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )

    assert page_observations(first) == page_observations(second)


def test_fingerprint_changes_when_bounded_page_content_changes() -> None:
    before = CrawlResult(
        pages=(
            CrawledPage(
                _page("https://example.com/", "<html><title>Old</title></html>"),
                depth=0,
            ),
        ),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )
    after = CrawlResult(
        pages=(
            CrawledPage(
                _page("https://example.com/", "<html><title>New</title></html>"),
                depth=0,
            ),
        ),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )

    assert page_observations(before)[0].fingerprint != page_observations(after)[0].fingerprint


def test_noindex_and_observation_records_remain_machine_comparable() -> None:
    result = CrawlResult(
        pages=(
            CrawledPage(
                _page(
                    "https://example.com/private",
                    '<html><meta name="robots" content="noindex"><h1>Private</h1></html>',
                ),
                depth=1,
            ),
        ),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )

    pages = page_observations(result)
    records = observation_records(pages)

    assert pages[0].indexable is False
    assert [(item.key, item.state) for item in records] == [
        ("page.fingerprint", pages[0].fingerprint),
        ("page.http-status", "200"),
        ("page.indexable", "false"),
    ]
