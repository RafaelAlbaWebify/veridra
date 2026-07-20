from __future__ import annotations

from datetime import UTC, datetime

from veridra.core import Assessment, Finding, Status
from veridra.reports import render_report


def test_report_escapes_target_derived_content() -> None:
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="test.escape",
                area="Website health",
                title="Unsafe <script>alert(1)</script>",
                status=Status.attention,
                severity="medium",
                summary="Observed <b>markup</b>.",
                recommendation="Use > safe output.",
                evidence={"value": "<img src=x onerror=alert(1)>"},
            )
        ],
    )

    report = render_report(assessment)

    assert "<script>alert(1)</script>" not in report
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
    assert "&lt;img src=x onerror=alert(1)&gt;" in report


def test_report_contains_scope_metadata_area_and_priorities() -> None:
    generated = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="test.attention",
                area="Website health",
                title="Attention",
                status=Status.attention,
                severity="medium",
                summary="Needs attention.",
                recommendation="Fix the issue.",
            )
        ],
        mode="live",
        generated_at=generated,
        elapsed_ms=125,
    )
    report = render_report(assessment)

    assert "This is not a penetration test" in report
    assert "window.print()" in report
    assert "Priority actions" in report
    assert "The first five attention findings" in report
    assert "Fix the issue." in report
    assert "Evidence-backed findings" in report
    assert "Assessment areas" in report
    assert "2026-07-20T12:00:00+00:00" in report
    assert "125 ms" in report
    assert "Website health" in report


def test_report_priority_actions_are_capped_at_five() -> None:
    findings = [
        Finding(
            id=f"finding-{index}",
            area="Website health",
            title=f"Priority finding {index}",
            status=Status.attention,
            severity="medium",
            summary="Needs attention.",
            recommendation="Fix it.",
        )
        for index in range(7)
    ]

    report = render_report(Assessment.build("https://example.com", findings))

    assert report.count("Needs attention.") == 12
    assert report.count("Priority finding 4") == 2
    assert report.count("Priority finding 5") == 1
    assert report.count("Priority finding 6") == 1
