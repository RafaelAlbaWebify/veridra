from __future__ import annotations

from veridra.collector import PageEvidence
from veridra.crawl import CrawlResult, CrawledPage
from veridra.core import Status
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


def _by_id(body: str, headers: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
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
    assert {identifier for identifier in expected if findings[identifier].status == Status.attention} == expected
    cookie_evidence = findings["security.cookie-flags"].evidence["affected_pages"]
    assert cookie_evidence[0]["missing_flags"] == ["Secure", "HttpOnly", "SameSite"]


def test_relative_same_origin_form_is_not_cross_origin() -> None:
    finding = _by_id("<form action='/contact'></form>")[
        "security.cross-origin-forms"
    ]
    assert finding.status == Status.passed
