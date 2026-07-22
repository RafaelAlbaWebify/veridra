# ruff: noqa: I001
from __future__ import annotations

import base64
import zipfile
from io import BytesIO

import pytest
from pydantic import ValidationError

from veridra.core import demo_assessment
from veridra.exports import build_evidence_package
from veridra.report_profiles import REPORT_SECTIONS, ReportProfile
from veridra.reports import render_report


def test_default_report_branding_is_preserved() -> None:
    report = render_report(demo_assessment())
    assert "Veridra assessment report" in report
    assert '<html lang="en">' in report
    assert "Evidence</th>" in report
    assert "Executive summary" in report
    assert "Implementation roadmap" in report


def test_custom_profile_is_applied_and_escaped() -> None:
    profile = ReportProfile(
        organisation_name="Agency <script>",
        client_name="Client & Co",
        consultant_name="Rafael <Admin>",
        agency_email="hello@example.com",
        agency_phone="+34 <123>",
        agency_website="https://example.com/contact?x=1&y=2",
        accent_colour="#123ABC",
        cover_title="Audit <cover>",
        introduction="Review <strong>carefully</strong>.",
        executive_summary="Executive <summary>",
        conclusion="Conclusion <safe>",
        call_to_action_label="Book <now>",
        call_to_action_url="https://example.com/book?x=1&y=2",
        language="es",
        show_raw_evidence=False,
    )
    report = render_report(demo_assessment(), profile)

    assert "Audit &lt;cover&gt;" in report
    assert "Client &amp; Co" in report
    assert "Rafael &lt;Admin&gt;" in report
    assert "+34 &lt;123&gt;" in report
    assert "Review &lt;strong&gt;carefully&lt;/strong&gt;." in report
    assert "Executive &lt;summary&gt;" in report
    assert "Conclusion &lt;safe&gt;" in report
    assert "Book &lt;now&gt;" in report
    assert "https://example.com/book?x=1&amp;y=2" in report
    assert "#123abc" in report
    assert '<html lang="es">' in report
    assert "Evidence</th>" not in report
    assert "<pre>" not in report


def test_selected_areas_recalculate_report_and_exclude_other_findings() -> None:
    assessment = demo_assessment()
    selected_area = assessment.findings[0].area
    excluded = next(item for item in assessment.findings if item.area != selected_area)
    profile = ReportProfile(selected_areas=(selected_area,))

    report = render_report(assessment, profile)

    assert selected_area in report
    assert excluded.title not in report
    assert f"<strong>{sum(item.area == selected_area for item in assessment.findings)}</strong>" in report


def test_section_order_controls_presence_and_order() -> None:
    profile = ReportProfile(
        section_order=("conclusion", "executive_summary", "findings"),
        conclusion="Final recommendation.",
    )
    report = render_report(demo_assessment(), profile)

    assert report.index("Conclusion") < report.index("Executive summary")
    assert "Priority actions" not in report
    assert "Business-impact view" not in report
    assert "Evidence-backed findings" in report


def test_embedded_png_logo_is_preserved_without_remote_fetching() -> None:
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nsmall-logo").decode("ascii")
    logo = f"data:image/png;base64,{encoded}"
    report = render_report(demo_assessment(), ReportProfile(logo_data_uri=logo))
    assert html_escape(logo) in report
    assert "class='logo'" in report


def html_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("'", "&#x27;")


def test_profile_rejects_unsafe_or_invalid_values() -> None:
    with pytest.raises(ValidationError):
        ReportProfile(accent_colour="red")
    with pytest.raises(ValidationError):
        ReportProfile(call_to_action_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        ReportProfile(language="fr")
    with pytest.raises(ValidationError):
        ReportProfile(section_order=("findings", "findings"))
    with pytest.raises(ValidationError):
        ReportProfile(section_order=("unknown",))
    with pytest.raises(ValidationError):
        ReportProfile(logo_data_uri="https://example.com/logo.png")
    with pytest.raises(ValidationError):
        ReportProfile(logo_data_uri="data:image/svg+xml;base64,PHN2Zz4=")
    with pytest.raises(ValidationError):
        ReportProfile(logo_data_uri="data:image/png;base64,bm90LXBuZw==")


def test_section_catalog_is_stable_and_complete() -> None:
    assert REPORT_SECTIONS == (
        "executive_summary",
        "priority_actions",
        "business_impact",
        "implementation_roadmap",
        "assessment_areas",
        "findings",
        "conclusion",
        "call_to_action",
    )


def test_evidence_package_uses_the_same_custom_report() -> None:
    assessment = demo_assessment()
    profile = ReportProfile(
        organisation_name="Example Agency",
        cover_title="Client website review",
        conclusion="Proceed with the prioritised remediation plan.",
        section_order=("executive_summary", "findings", "conclusion"),
        show_raw_evidence=False,
    )
    package = build_evidence_package(assessment, profile)

    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        report = archive.read("report.html").decode("utf-8")

    assert report == render_report(assessment, profile)
    assert "Client website review" in report
    assert "Proceed with the prioritised remediation plan." in report
    assert "Evidence</th>" not in report
