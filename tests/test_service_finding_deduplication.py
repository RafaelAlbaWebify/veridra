from __future__ import annotations

from veridra.core import Finding, Status
from veridra.service import _suppress_redundant_live_findings


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
