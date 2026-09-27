from __future__ import annotations

from veridra.collector import PageEvidence, SiteEvidence
from veridra.core import Finding, Status
from veridra.service import (
    LIVE_FINDING_IDS,
    _deduplicate_finding_ids,
    _suppress_redundant_live_findings,
    _transport_findings,
)


def _finding(identifier: str) -> Finding:
    return Finding(
        id=identifier,
        area="test",
        title=identifier,
        status=Status.attention,
        severity="medium",
        summary=identifier,
    )


def test_suppress_redundant_live_findings_keeps_richer_signals() -> None:
    findings = [
        _finding("health.language"),
        _finding("accessibility.document-language"),
        _finding("health.title"),
        _finding("crawl.title"),
        _finding("ai.structured-data"),
        _finding("local.structured-business"),
        _finding("health.viewport"),
        _finding("accessibility.viewport"),
        _finding("search.canonical"),
        _finding("crawl.canonical"),
        _finding("search.description"),
        _finding("crawl.description"),
        _finding("trust.heading"),
        _finding("crawl.h1"),
        _finding("accessibility.image-alt"),
        _finding("crawl.image-alt"),
        _finding("crawl.mixed-content"),
        _finding("security.mixed-content"),
        _finding("security.insecure-resources"),
        _finding("content.placeholder-default"),
    ]

    result = _suppress_redundant_live_findings(findings)
    identifiers = {item.id for item in result}

    assert identifiers == {
        "accessibility.document-language",
        "crawl.title",
        "local.structured-business",
        "accessibility.viewport",
        "crawl.canonical",
        "crawl.description",
        "crawl.h1",
        "crawl.image-alt",
        "security.insecure-resources",
        "content.placeholder-default",
    }


def test_suppress_redundant_live_findings_keeps_basic_signal_without_replacement() -> None:
    findings = [_finding("health.language"), _finding("content.placeholder-default")]

    result = _suppress_redundant_live_findings(findings)

    assert [item.id for item in result] == [
        "health.language",
        "content.placeholder-default",
    ]


def test_deduplicate_finding_ids_keeps_stronger_richer_attention() -> None:
    weak = _finding("crawl.duplicate-titles")
    strong = Finding(
        id="crawl.duplicate-titles",
        area="Search visibility",
        title="Duplicate document titles",
        status=Status.attention,
        severity="medium",
        summary="richer",
        evidence={
            "duplicate_groups": [
                {
                    "value": "Example",
                    "urls": ["https://example.test/a", "https://example.test/b"],
                }
            ]
        },
    )
    passed = Finding(
        id="crawl.duplicate-titles",
        area="Search visibility",
        title="Duplicate document titles",
        status=Status.passed,
        severity="info",
        summary="passed",
    )

    result = _deduplicate_finding_ids([weak, passed, strong])

    assert len(result) == 1
    assert result[0].status == Status.attention
    assert result[0].evidence == strong.evidence


def test_intermediate_homepage_response_is_unavailable_not_healthy() -> None:
    homepage = PageEvidence(
        requested_url="https://example.test/",
        final_url="https://example.test/",
        status_code=202,
        headers={"content-type": "text/html"},
        body="Accepted",
        redirect_chain=(),
        connected_ip="93.184.216.34",
        validated_ips=("93.184.216.34",),
    )
    findings = {
        finding.id: finding
        for finding in _transport_findings(SiteEvidence(homepage=homepage, robots=None))
    }

    response = findings["health.http-status"]
    assert response.status == Status.unavailable
    assert response.severity == "low"
    assert "not treated as representative page content" in response.summary



def test_known_live_producer_ids_are_registered() -> None:
    producer_ids = {
        "health.http-status",
        "search.robots-availability",
        "crawl.effective-limits",
        "search.indexable",
        "search.sitemap",
        "ai.structured-data",
        "ai.open-graph-title",
        "ai.open-graph-description",
        "trust.about",
        "trust.contact",
        "trust.privacy",
        "trust.terms",
        "security.hsts",
        "security.csp",
        "security.nosniff",
        "security.frames",
        "security.referrer",
        "security.permissions",
        "ai.oai-searchbot",
        "ai.gptbot",
        "ai.google-extended",
        "ai.googlebot",
        "crawl.http-status",
        "crawl.title",
        "crawl.description",
        "crawl.h1",
        "crawl.canonical",
        "crawl.mixed-content",
        "crawl.broken-internal-links",
        "crawl.retrieval-coverage",
        "crawl.duplicate-titles",
        "crawl.duplicate-descriptions",
        "crawl.image-alt",
        "crawl.redirect-chains",
        "crawl.oversized-html",
        "crawl.page-size",
        "content.placeholder-default",
        "content.explicit-update-age",
        "content.opening-hours-consistency",
        "accessibility.document-language",
        "accessibility.viewport",
        "accessibility.form-labels",
        "accessibility.interactive-names",
        "accessibility.image-alt",
        "accessibility.heading-order",
        "accessibility.duplicate-ids",
        "security.cookie-flags",
        "security.cross-origin-forms",
        "security.insecure-form-actions",
        "security.target-blank-isolation",
        "security.insecure-resources",
        "security.server-disclosure",
        "security.csp-unsafe-directives",
        "local.structured-business",
        "local.structured-name",
        "local.structured-url",
        "local.structured-phone",
        "local.structured-address",
        "local.structured-hours",
        "local.structured-same-as",
        "local.visible-phone",
        "local.visible-address",
        "local.visible-hours",
        "local.map-link",
        "local.location-route",
        "dns.nameservers",
        "email.mx",
        "email.spf",
        "email.dmarc",
    }

    assert producer_ids == LIVE_FINDING_IDS
