from __future__ import annotations

from veridra.collector import PageEvidence
from veridra.commercial_crawl_findings import analyze_commercial_crawl_findings
from veridra.core import Finding, Status
from veridra.crawl import CrawledPage, CrawlResult


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


def _findings(result: CrawlResult) -> dict[str, Finding]:
    return {finding.id: finding for finding in analyze_commercial_crawl_findings(result)}


def test_duplicate_metadata_is_normalized_and_empty_values_are_ignored() -> None:
    result = _result(
        _page(
            "https://example.com/a",
            "<title>  Shared   Title </title>"
            "<meta name='description' content=' Shared description '>",
        ),
        _page(
            "https://example.com/about",
            "<title>About</title><meta name='description' content='About'>"
            "<meta property='og:title' content='About'>"
            "<meta property='og:description' content='About'>",
        ),
        _page(
            "https://example.com/contact",
            "<title>Contact</title><meta name='description' content='Contact'>"
            "<meta property='og:title' content='Contact'>"
            "<meta property='og:description' content='Contact'>",
        ),
        _page(
            "https://example.com/privacy",
            "<title>Privacy</title><meta name='description' content='Privacy'>"
            "<meta property='og:title' content='Privacy'>"
            "<meta property='og:description' content='Privacy'>",
        ),
        _page(
            "https://example.com/terms",
            "<title>Terms</title><meta name='description' content='Terms'>"
            "<meta property='og:title' content='Terms'>"
            "<meta property='og:description' content='Terms'>",
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
            "<meta property='og:title' content='A'>"
            "<meta property='og:description' content='A page'>"
            "<script type='application/ld+json'>{}</script>"
            "<img src='decorative.jpg' alt=''>",
        ),
        _page(
            "https://example.com/b",
            "<title>B</title><meta name='description' content='B page'>"
            "<meta property='og:title' content='B'>"
            "<meta property='og:description' content='B page'>"
            "<img src='useful.jpg' alt='Useful'>",
        ),
    )

    assert all(
        finding.status is Status.passed
        for finding in analyze_commercial_crawl_findings(result)
    )


def test_indexability_social_structured_data_and_trust_page_evidence() -> None:
    result = _result(
        _page(
            "https://example.com/",
            "<title>Home</title>"
            "<meta name='description' content='Home'>"
            "<meta name='robots' content='index, noindex'>"
            "<meta property='og:title' content='Home'>",
        ),
        _page(
            "https://example.com/privacy",
            "<title>Privacy</title>"
            "<meta name='description' content='Privacy'>"
            "<meta property='og:title' content='Privacy'>"
            "<meta property='og:description' content='Privacy'>"
            "<script type='application/ld+json'>{}</script>",
        ),
    )

    findings = _findings(result)

    indexability = findings["crawl.indexability"]
    assert indexability.status is Status.attention
    assert indexability.evidence["affected_pages"] == [
        {"url": "https://example.com/", "sources": ["meta robots"]}
    ]

    social = findings["crawl.social-metadata"]
    assert social.status is Status.attention
    assert social.evidence["affected_pages"] == [
        {
            "url": "https://example.com/",
            "missing_properties": ["og:description"],
        }
    ]

    structured = findings["crawl.structured-data-coverage"]
    assert structured.status is Status.passed
    assert structured.evidence["pages_with_json_ld"] == [
        "https://example.com/privacy"
    ]

    trust = findings["crawl.trust-pages"]
    assert trust.status is Status.attention
    assert trust.evidence["missing_categories"] == ["about", "contact", "terms"]
    assert trust.evidence["observed_categories"] == {
        "privacy": ["https://example.com/privacy"]
    }
