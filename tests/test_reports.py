from __future__ import annotations

from datetime import UTC, datetime

from veridra.core import Assessment, Finding, Status
from veridra.report_profiles import ReportProfile
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

    report = render_report(assessment, ReportProfile(show_raw_evidence=True))

    assert "<script>alert(1)</script>" not in report
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
    assert "&lt;img src=x onerror=alert(1)&gt;" in report


def test_report_contains_scope_metadata_areas_and_executive_sections() -> None:
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
    assert "@media print" in report
    assert "Executive summary" in report
    assert "Priority actions" in report
    assert "Business-impact view" in report
    assert "Implementation roadmap" in report
    assert "Fix the issue." in report
    assert "Evidence-backed findings" in report
    assert "Assessment areas" in report
    assert "2026-07-20T12:00:00+00:00" in report
    assert "125 ms" in report
    assert "Website health" in report


def test_report_priority_actions_are_capped_at_ten() -> None:
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
        for index in range(12)
    ]

    report = render_report(Assessment.build("https://example.com", findings))
    priority_list = report.split("<ol class='priority-list'>", 1)[1].split("</ol>", 1)[0]

    assert priority_list.count("<li>") == 10
    assert "Priority finding 0" in priority_list
    assert "Priority finding 11" in priority_list
    assert "Priority finding 8" not in priority_list
    assert "Priority finding 9" not in priority_list
    assert "Priority finding 8" in report
    assert "Priority finding 9" in report


def test_report_surfaces_bounded_affected_pages_without_raw_evidence() -> None:
    urls = [f"https://example.com/page-{index}" for index in range(12)]
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="crawl.title",
                area="Search visibility",
                title="Document title",
                status=Status.attention,
                severity="medium",
                summary="Some crawled pages are missing a document title.",
                recommendation="Add a descriptive title to each affected page.",
                evidence={"affected_urls": urls, "internal_debug": "not customer-facing"},
            )
        ],
    )

    report = render_report(assessment)

    assert "Affected pages" in report
    for url in sorted(urls)[:10]:
        assert url in report
    for url in sorted(urls)[10:]:
        assert url not in report
    assert "+ 2 more affected pages" in report
    assert "internal_debug" not in report


def test_report_surfaces_urls_from_structured_affected_pages() -> None:
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="security.insecure-resources",
                area="Security posture",
                title="Active HTTP subresources",
                status=Status.attention,
                severity="high",
                summary="One crawled page references an active HTTP subresource.",
                recommendation="Move the resource to HTTPS.",
                evidence={
                    "affected_pages": [
                        {
                            "url": "https://example.com/contact",
                            "resource": "http://cdn.example.com/form.js",
                        }
                    ],
                    "bounded_examples": 10,
                },
            )
        ],
    )

    report = render_report(assessment)

    assert "Affected pages" in report
    assert "https://example.com/contact" in report
    assert "http://cdn.example.com/form.js" not in report


def test_report_surfaces_affected_pages_from_known_grouped_evidence_shapes() -> None:
    findings = [
        Finding(
            id="crawl.duplicate-titles",
            area="Search visibility",
            title="Duplicate titles",
            status=Status.attention,
            severity="medium",
            summary="Duplicate titles were observed.",
            evidence={
                "duplicate_groups": [
                    {"value": "Shared", "urls": ["https://example.com/b", "https://example.com/a"]}
                ]
            },
        ),
        Finding(
            id="content.explicit-update-age",
            area="Trust and content quality",
            title="Old update label",
            status=Status.attention,
            severity="low",
            summary="An old update label was observed.",
            evidence={
                "indicators": [
                    {
                        "url": "https://example.com/old",
                        "age_months_at_assessment": 24,
                    }
                ]
            },
        ),
        Finding(
            id="content.opening-hours-consistency",
            area="Local presence",
            title="Opening hours conflict",
            status=Status.attention,
            severity="high",
            summary="Conflicting hours were observed.",
            evidence={
                "conflicts": [
                    {
                        "first_url": "https://example.com/contact",
                        "second_url": "https://example.com/hours",
                        "differences": [{"day": "Monday"}],
                    }
                ]
            },
        ),
    ]

    report = render_report(Assessment.build("https://example.com", findings))

    for url in (
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/old",
        "https://example.com/contact",
        "https://example.com/hours",
    ):
        assert url in report


def test_report_surfaces_final_pages_from_redirect_chain_evidence() -> None:
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="crawl.redirect-chains",
                area="Website health",
                title="Internal redirect chains",
                status=Status.attention,
                severity="medium",
                summary="One multi-hop redirect chain was observed.",
                evidence={
                    "chains": [
                        {
                            "requested_url": "https://example.com/old",
                            "final_url": "https://example.com/new",
                            "redirect_chain": [
                                "https://example.com/middle",
                                "https://example.com/new",
                            ],
                        }
                    ]
                },
            )
        ],
    )

    report = render_report(assessment)

    assert "Affected pages" in report
    assert "https://example.com/new" in report
    assert "https://example.com/middle" not in report



def test_spanish_report_localizes_customer_facing_structure() -> None:
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="crawl.title",
                area="Search visibility",
                title="Document title",
                status=Status.attention,
                severity="medium",
                summary="One crawled page needs attention.",
                evidence={"affected_urls": ["https://example.com/contact"]},
            )
        ],
    )
    profile = ReportProfile(
        organisation_name="Agencia",
        client_name="Cliente",
        language="es",
        conclusion="Revisar las acciones propuestas.",
        call_to_action_label="Solicitar revisión",
        call_to_action_url="https://example.com/contacto",
    )

    report = render_report(assessment, profile)

    assert '<html lang="es">' in report
    assert "Resumen ejecutivo" in report
    assert "Acciones prioritarias" in report
    assert "Impacto en el negocio" in report
    assert "Plan de implementación" in report
    assert "Áreas de evaluación" in report
    assert "Hallazgos respaldados por evidencia" in report
    assert "Páginas afectadas" in report
    assert "Conclusión" in report
    assert "Siguiente paso" in report
    assert "Preparado para:" in report
