from __future__ import annotations

from veridra.collector import PageEvidence
from veridra.commercial_crawl_findings import analyze_commercial_crawl_findings
from veridra.core import Status
from veridra.crawl import CrawlResult, CrawledPage


def _page(
    url: str,
    body: str,
    *,
    requested_url: str | None = None,
    redirect_chain: tuple[str, ...] = (),
) -> CrawledPage:
    return CrawledPage(
        evidence=PageEvidence(
            requested_url=requested_url or url,
            final_url=url,
            status_code=200,
            headers={"content-type": "text/html"},
            body=body,
            redirect_chain=redirect_chain,
            connected_ip="93.184.216.34",
            validated_ips=("93.184.216.34",),
        ),
        depth=0,
    )


def _result(*pages: CrawledPage) -> CrawlResult:
    return CrawlResult(
        pages=pages,
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )


def _findings(result: CrawlResult) -> dict[str, object]:
    return {finding.id: finding for finding in analyze_commercial_crawl_findings(result)}


def test_duplicate_metadata_is_normalized_and_empty_values_are_ignored() -> None:
    result = _result(
        _page(
            "https://example.com/a",
            "<title>  Shared   Title </title>"
            "<meta name='description' content=' Shared description '>",
        ),
        _page(
            "https://example.com/b",
            "<title>shared title</title>"
            "<meta name='description' content='shared   description'>",
        ),
        _page(
            "https://example.com/c",
            "<title>Unique</title><meta name='description' content=''>",
        ),
    )
    findings = _findings(result)
    titles = findings["crawl.duplicate-titles"]
    descriptions = findings["crawl.duplicate-descriptions"]

    assert titles.status is Status.attention
    assert titles.evidence["duplicate_groups"] == [
        {
            "value": "Shared Title",
            "normalized_value": "shared title",
            "urls": ["https://example.com/a", "https://example.com/b"],
        }
    ]
    assert descriptions.status is Status.attention
    assert descriptions.evidence["duplicate_groups"] == [
        {
            "value": "Shared description",
            "normalized_value": "shared description",
            "urls": ["https://example.com/a", "https://example.com/b"],
        }
    ]


def test_missing_alt_counts_only_images_without_the_attribute() -> None:
    result = _result(
        _page(
            "https://example.com/gallery",
            "<img src='one.jpg'><img src='two.jpg' alt=''>"
            "<img src='three.jpg' alt='Description'><img src='four.jpg'>",
        )
    )
    finding = _findings(result)["crawl.image-alt"]

    assert finding.status is Status.attention
    assert finding.evidence["affected_pages"] == [
        {"url": "https://example.com/gallery", "missing_alt_count": 2}
    ]
    assert finding.evidence["affected_urls"] == ["https://example.com/gallery"]


def test_redirect_chain_and_oversized_html_evidence_is_bounded_and_explicit() -> None:
    oversized_body = "x" * 500_001
    result = _result(
        _page(
            "https://example.com/final",
            oversized_body,
            requested_url="https://example.com/start",
            redirect_chain=(
                "https://example.com/middle",
                "https://example.com/final",
            ),
        ),
        _page(
            "https://example.com/one-hop",
            "ok",
            requested_url="https://example.com/old",
            redirect_chain=("https://example.com/one-hop",),
        ),
    )
    findings = _findings(result)
    redirects = findings["crawl.redirect-chains"]
    oversized = findings["crawl.oversized-html"]

    assert redirects.status is Status.attention
    assert redirects.evidence["redirect_chains"] == [
        {
            "requested_url": "https://example.com/start",
            "final_url": "https://example.com/final",
            "redirect_chain": [
                "https://example.com/middle",
                "https://example.com/final",
            ],
        }
    ]
    assert oversized.status is Status.attention
    assert oversized.evidence["threshold_bytes"] == 500_000
    assert oversized.evidence["measurement"] == "decoded collected HTML body bytes"
    assert oversized.evidence["affected_pages"] == [
        {"url": "https://example.com/final", "html_body_bytes": 500_001}
    ]


def test_clean_pages_produce_passed_findings() -> None:
    result = _result(
        _page(
            "https://example.com/a",
            "<title>A</title><meta name='description' content='A page'>"
            "<img src='decorative.jpg' alt=''>",
        ),
        _page(
            "https://example.com/b",
            "<title>B</title><meta name='description' content='B page'>"
            "<img src='useful.jpg' alt='Useful'>",
        ),
    )

    assert all(
        finding.status is Status.passed
        for finding in analyze_commercial_crawl_findings(result)
    )
