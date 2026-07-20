import pytest

from veridra.core import Status, UnsafeTargetError, analyze_document, demo_assessment, normalize_url


def test_normalize_url() -> None:
    assert normalize_url("example.com") == "https://example.com"


def test_credentials_rejected() -> None:
    with pytest.raises(UnsafeTargetError):
        normalize_url("https://user:pass@example.com")


def test_document_analysis() -> None:
    findings = {item.id: item for item in analyze_document("<title>A</title><h1>A</h1>", {})}
    assert findings["health.title"].status == Status.passed
    assert findings["security.csp"].status == Status.attention


def test_demo_summary() -> None:
    assessment = demo_assessment()
    assert assessment.summary["total"] == len(assessment.findings)
