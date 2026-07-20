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


def test_report_contains_scope_metadata_and_area_summary() -> None:
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
            )
        ],
        mode="live",
        generated_at=generated,
        elapsed_ms=125,
    )
    report = render_report(assessment)

    assert "This is not a penetration test" in report
    assert "window.print()" in report
    assert "Evidence-backed findings" in report
    assert "Assessment areas" in report
    assert "2026-07-20T12:00:00+00:00" in report
    assert "125 ms" in report
    assert "Website health" in report
