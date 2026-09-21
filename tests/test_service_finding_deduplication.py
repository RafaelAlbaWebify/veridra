from __future__ import annotations

from veridra.core import Finding, Status
from veridra.service import _deduplicate_finding_ids, _suppress_redundant_live_findings


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
