from datetime import UTC, datetime

import pytest

from veridra.core import (
    Assessment,
    Finding,
    Status,
    UnsafeTargetError,
    analyze_document,
    demo_assessment,
    normalize_url,
)


def test_normalize_url() -> None:
    assert normalize_url("example.com") == "https://example.com"


def test_credentials_rejected() -> None:
    with pytest.raises(UnsafeTargetError):
        normalize_url("https://user:pass@example.com")


def test_document_analysis() -> None:
    findings = {
        item.id: item
        for item in analyze_document("<title>A</title><h1>A</h1>", {})
    }
    assert findings["health.title"].status == Status.passed
    assert findings["security.csp"].status == Status.attention


def test_meta_noindex_and_mixed_content_are_detected() -> None:
    html = """
    <html><head>
      <meta name="robots" content="noindex,nofollow">
      <script src="http://example.com/app.js"></script>
    </head></html>
    """
    findings = {item.id: item for item in analyze_document(html, {})}
    assert findings["search.indexable"].status == Status.attention
    assert findings["security.mixed-content"].status == Status.attention


def test_extended_security_headers_pass() -> None:
    headers = {
        "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=()",
        "Strict-Transport-Security": "max-age=31536000",
        "X-Content-Type-Options": "nosniff",
    }
    findings = {item.id: item for item in analyze_document("", headers)}
    assert findings["security.frames"].status == Status.passed
    assert findings["security.referrer"].status == Status.passed
    assert findings["security.permissions"].status == Status.passed


def test_crawler_groups_are_evaluated_independently() -> None:
    robots = """
    User-agent: *
    Disallow: /

    User-agent: OAI-SearchBot
    Allow: /
    """
    findings = {item.id: item for item in analyze_document("", {}, robots)}
    assert findings["ai.oai-searchbot"].status == Status.passed
    assert findings["ai.gptbot"].status == Status.attention
    assert findings["ai.googlebot"].status == Status.attention


def test_passive_trust_and_discoverability_signals_pass() -> None:
    html = """
    <html lang="en"><head>
      <meta name="description" content="A useful description">
      <meta property="og:title" content="Example">
      <meta property="og:description" content="Example description">
    </head><body>
      <a href="/company">Who we are</a>
      <a href="/get-in-touch">Reach us</a>
      <a href="/data-protection">Privacy</a>
      <a href="/legal">Terms and conditions</a>
    </body></html>
    """
    robots = "Sitemap: https://example.com/sitemap.xml"
    findings = {item.id: item for item in analyze_document(html, {}, robots)}

    for identifier in (
        "health.language",
        "search.description",
        "search.sitemap",
        "ai.open-graph-title",
        "ai.open-graph-description",
        "trust.about",
        "trust.contact",
        "trust.privacy",
        "trust.terms",
    ):
        assert findings[identifier].status == Status.passed
    assert findings["health.language"].evidence == {"language": "en"}
    assert findings["search.sitemap"].evidence == {
        "sitemaps": ["https://example.com/sitemap.xml"]
    }


def test_missing_passive_signals_require_attention() -> None:
    findings = {item.id: item for item in analyze_document("<html></html>", {})}
    assert findings["health.language"].status == Status.attention
    assert findings["search.description"].status == Status.attention
    assert findings["search.sitemap"].status == Status.attention
    assert findings["trust.privacy"].status == Status.attention


def test_assessment_metadata_area_summary_and_ordering() -> None:
    generated_at = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    findings = [
        Finding(
            id="passed",
            area="Website health",
            title="Passed item",
            status=Status.passed,
            severity="info",
            summary="Passed.",
        ),
        Finding(
            id="unavailable",
            area="Search visibility",
            title="Unavailable item",
            status=Status.unavailable,
            severity="low",
            summary="Unavailable.",
        ),
        Finding(
            id="attention",
            area="Website health",
            title="Attention item",
            status=Status.attention,
            severity="high",
            summary="Attention.",
        ),
    ]

    assessment = Assessment.build(
        "https://example.com",
        findings,
        mode="live",
        generated_at=generated_at,
        elapsed_ms=125,
    )

    assert assessment.schema_version == "1.3"
    assert assessment.mode == "live"
    assert assessment.generated_at == generated_at
    assert assessment.elapsed_ms == 125
    assert [item.id for item in assessment.findings] == [
        "attention",
        "unavailable",
        "passed",
    ]
    assert assessment.area_summary["Website health"] == {
        "passed": 1,
        "attention": 1,
        "unavailable": 0,
        "total": 2,
    }


def test_demo_summary() -> None:
    assessment = demo_assessment()
    assert assessment.mode == "demo"
    assert assessment.summary["total"] == len(assessment.findings)
    assert sum(values["total"] for values in assessment.area_summary.values()) == len(
        assessment.findings
    )
