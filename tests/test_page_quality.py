# ruff: noqa: I001
from __future__ import annotations

from veridra.collector import PageEvidence
from veridra.core import Status
from veridra.crawl import CrawlResult, CrawledPage
from veridra.page_quality import analyze_page_quality


def _page(
    url: str,
    body: str,
    *,
    requested_url: str | None = None,
    redirect_chain: tuple[str, ...] = (),
) -> CrawledPage:
    evidence = PageEvidence(
        requested_url=requested_url or url,
        final_url=url,
        status_code=200,
        headers={"content-type": "text/html"},
        body=body,
        redirect_chain=redirect_chain,
        connected_ip="93.184.216.34",
        validated_ips=("93.184.216.34",),
    )
    return CrawledPage(evidence=evidence, depth=0)


def _result(*pages: CrawledPage) -> CrawlResult:
    return CrawlResult(
        pages=pages,
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )


def test_duplicate_non_empty_metadata_is_grouped() -> None:
    first = _page(
        "https://example.com/one",
        "<title> Shared   title </title>"
        "<meta name='description' content='Shared description'>",
    )
    second = _page(
        "https://example.com/two",
        "<title>Shared title</title>"
        "<meta name='description' content='Shared description'>",
    )
    findings = {item.id: item for item in analyze_page_quality(_result(first, second))}

    titles = findings["crawl.duplicate-titles"]
    assert titles.status == Status.attention
    assert titles.evidence["duplicate_groups"] == [
        {
            "value": "Shared title",
            "urls": ["https://example.com/one", "https://example.com/two"],
            "count": 2,
        }
    ]
    descriptions = findings["crawl.duplicate-descriptions"]
    assert descriptions.status == Status.attention


def test_missing_metadata_does_not_create_duplicate_groups() -> None:
    findings = {
        item.id: item
        for item in analyze_page_quality(
            _result(
                _page("https://example.com/one", "<html></html>"),
                _page("https://example.com/two", "<html></html>"),
            )
        )
    }
    assert findings["crawl.duplicate-titles"].status == Status.passed
    assert findings["crawl.duplicate-descriptions"].status == Status.passed


def test_image_alt_check_distinguishes_missing_from_empty_alt() -> None:
    page = _page(
        "https://example.com/",
        "<img src='missing.png'><img src='decorative.png' alt=''>",
    )
    finding = {
        item.id: item for item in analyze_page_quality(_result(page))
    }["crawl.image-alt"]

    assert finding.status == Status.attention
    assert finding.evidence["affected_pages"] == [
        {"url": "https://example.com/", "missing_alt_images": 1}
    ]


def test_redirect_chain_and_html_body_size_are_reported() -> None:
    redirected = _page(
        "https://example.com/final",
        "<title>Final</title>",
        requested_url="https://example.com/start",
        redirect_chain=(
            "https://example.com/middle",
            "https://example.com/final",
        ),
    )
    large = _page("https://example.com/large", "x" * 500_001)
    findings = {item.id: item for item in analyze_page_quality(_result(redirected, large))}

    chains = findings["crawl.redirect-chains"]
    assert chains.status == Status.attention
    assert chains.evidence["chains"] == [
        {
            "requested_url": "https://example.com/start",
            "final_url": "https://example.com/final",
            "redirect_chain": [
                "https://example.com/middle",
                "https://example.com/final",
            ],
            "hop_count": 2,
        }
    ]

    page_size = findings["crawl.page-size"]
    assert page_size.status == Status.attention
    assert page_size.evidence["affected_pages"] == [
        {"url": "https://example.com/large", "html_body_bytes": 500_001}
    ]
    assert page_size.evidence["measurement"] == (
        "decoded HTML body encoded as UTF-8; not browser transfer size"
    )


def test_clean_pages_pass_all_quality_checks() -> None:
    page = _page(
        "https://example.com/",
        "<title>Unique</title>"
        "<meta name='description' content='Unique description'>"
        "<img src='decorative.png' alt=''>",
    )
    findings = analyze_page_quality(_result(page))
    assert all(item.status == Status.passed for item in findings)
