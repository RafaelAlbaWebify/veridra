from __future__ import annotations

from veridra.core import Finding, Status
from veridra.finding_value import ServiceClass, classify_finding_value


def _finding(identifier: str, severity: str = "medium") -> Finding:
    return Finding(
        id=identifier,
        area="test",
        title=identifier,
        status=Status.attention,
        severity=severity,
        summary=identifier,
    )


def test_owner_facing_content_is_activation_value() -> None:
    value = classify_finding_value(_finding("content.opening-hours-consistency", "high"))

    assert value.owner_understandable is True
    assert value.commercially_relevant is True
    assert value.webify_remediable is True
    assert value.service_class is ServiceClass.activation


def test_low_level_security_headers_are_monitor_only() -> None:
    value = classify_finding_value(_finding("security.permissions", "medium"))

    assert value.commercially_relevant is False
    assert value.service_class is ServiceClass.monitor_only


def test_material_security_issue_is_separate_quote() -> None:
    value = classify_finding_value(_finding("security.insecure-resources", "high"))

    assert value.commercially_relevant is True
    assert value.service_class is ServiceClass.separate_quote


def test_ai_readiness_does_not_claim_commercial_value() -> None:
    value = classify_finding_value(_finding("ai.open-graph-title", "medium"))

    # Explicit curated activation mappings may make metadata useful, but generic AI-only
    # signals remain informational unless independently justified.
    generic = classify_finding_value(_finding("ai.gptbot", "medium"))

    assert value.webify_remediable is True
    assert generic.commercially_relevant is False
    assert generic.service_class is ServiceClass.informational
