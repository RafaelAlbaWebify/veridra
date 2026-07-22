from __future__ import annotations

from veridra.accessibility import analyze_accessibility
from veridra.collector import PageEvidence
from veridra.core import Finding, Status
from veridra.crawl import CrawlResult, CrawledPage


def _result(body: str) -> CrawlResult:
    page = PageEvidence(
        requested_url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        headers={"content-type": "text/html"},
        body=body,
        redirect_chain=(),
        connected_ip="203.0.113.10",
        validated_ips=("203.0.113.10",),
    )
    return CrawlResult(
        pages=(CrawledPage(page, 0),),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )


def _by_id(body: str) -> dict[str, Finding]:
    return {item.id: item for item in analyze_accessibility(_result(body))}


def test_accessibility_clean_document_passes() -> None:
    findings = _by_id(
        """<html lang='en'><head><meta name='viewport' content='width=device-width'></head>
        <body><h1>Title</h1><h2>Section</h2><label for='email'>Email</label>
        <input id='email'><a href='/about'>About</a><button>Send</button>
        <img src='decorative.png' alt=''></body></html>"""
    )
    assert all(item.status == Status.passed for item in findings.values())


def test_accessibility_problem_document_reports_bounded_page_evidence() -> None:
    findings = _by_id(
        """<html><head></head><body><h1>Title</h1><h3>Skipped</h3>
        <input id='duplicate'><div id='duplicate'></div><a href='/'></a><button></button>
        <img src='missing.png'></body></html>"""
    )
    expected = {
        "accessibility.document-language",
        "accessibility.viewport",
        "accessibility.form-labels",
        "accessibility.interactive-names",
        "accessibility.image-alt",
        "accessibility.heading-order",
        "accessibility.duplicate-ids",
    }
    assert {
        identifier
        for identifier in expected
        if findings[identifier].status == Status.attention
    } == expected
    assert findings["accessibility.image-alt"].evidence["affected_urls"] == [
        "https://example.com/"
    ]


def test_explicit_empty_alt_is_not_missing() -> None:
    finding = _by_id("<html lang='en'><meta name='viewport' content='x'><img alt=''>")[
        "accessibility.image-alt"
    ]
    assert finding.status == Status.passed
