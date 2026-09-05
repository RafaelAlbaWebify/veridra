# ruff: noqa: I001
from __future__ import annotations

from veridra.collector import PageEvidence
from veridra.core import Finding, Status
from veridra.crawl import CrawlResult, CrawledPage
from veridra.passive_security import analyze_passive_security


def _result(body: str, headers: dict[str, str] | None = None) -> CrawlResult:
    page = PageEvidence(
        requested_url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        headers={"content-type": "text/html", **(headers or {})},
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


def _by_id(
    body: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Finding]:
    return {
        item.id: item
        for item in analyze_passive_security(_result(body, headers))
    }


def test_clean_passive_security_document_passes() -> None:
    findings = _by_id(
        "<form action='/submit'></form><a target='_blank' rel='noopener' href='https://example.com'>Safe</a>",
        {
            "set-cookie": "session=1; Secure; HttpOnly; SameSite=Lax",
            "content-security-policy": "default-src 'self'",
        },
    )
    assert all(item.status == Status.passed for item in findings.values())


def test_passive_security_problem_evidence() -> None:
    findings = _by_id(
        """<form action='http://forms.example.net/submit'></form>
        <a target='_blank' href='https://other.example'>Open</a>
        <script src='http://cdn.example/script.js'></script>""",
        {
            "set-cookie": "session=1",
            "server": "ExampleServer/1.0",
            "x-powered-by": "ExampleFramework",
            "content-security-policy": "script-src 'unsafe-inline' 'unsafe-eval'",
        },
    )
    expected = {
        "security.cookie-flags",
        "security.cross-origin-forms",
        "security.insecure-form-actions",
        "security.target-blank-isolation",
        "security.insecure-resources",
        "security.server-disclosure",
        "security.csp-unsafe-directives",
    }
    assert {
        identifier
        for identifier in expected
        if findings[identifier].status == Status.attention
    } == expected
    cookie_evidence = findings["security.cookie-flags"].evidence["affected_pages"]
    assert cookie_evidence[0]["missing_flags"] == ["Secure", "HttpOnly", "SameSite"]


def test_relative_same_origin_form_is_not_cross_origin() -> None:
    finding = _by_id("<form action='/contact'></form>")[
        "security.cross-origin-forms"
    ]
    assert finding.status == Status.passed


def test_http_anchor_and_profile_metadata_are_not_active_resources() -> None:
    findings = _by_id(
        """<a href='http://example.net/page'>Legacy link</a>
        <a href='http://facebook.com/sharer.php'>Share</a>
        <link rel='profile' href='http://gmpg.org/xfn/11'>"""
    )
    finding = findings["security.insecure-resources"]
    assert finding.status == Status.passed
    assert finding.title == "Insecure active resources"


def test_http_active_subresources_are_reported() -> None:
    findings = _by_id(
        """<script src='http://cdn.example/script.js'></script>
        <img src='http://cdn.example/image.jpg'>
        <link rel='stylesheet' href='http://cdn.example/site.css'>
        <video poster='http://cdn.example/poster.jpg'></video>"""
    )
    finding = findings["security.insecure-resources"]
    assert finding.status == Status.attention
    affected = finding.evidence["affected_pages"]
    assert affected[0]["resources"] == [
        "http://cdn.example/script.js",
        "http://cdn.example/image.jpg",
        "http://cdn.example/site.css",
        "http://cdn.example/poster.jpg",
    ]


def test_non_resource_link_rel_does_not_count_as_active_resource() -> None:
    findings = _by_id(
        """<link rel='canonical' href='http://example.com/'>
        <link rel='profile' href='http://gmpg.org/xfn/11'>
        <link rel='alternate' href='http://example.com/feed'>"""
    )
    assert findings["security.insecure-resources"].status == Status.passed
