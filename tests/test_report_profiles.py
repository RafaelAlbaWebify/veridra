from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from pydantic import ValidationError

from veridra.core import demo_assessment
from veridra.exports import build_evidence_package
from veridra.report_profiles import ReportProfile
from veridra.reports import render_report


def test_default_report_branding_is_preserved() -> None:
    report = render_report(demo_assessment())
    assert "Veridra assessment report" in report
    assert "<html lang=\"en\">" in report
    assert "Evidence</th>" in report


def test_custom_profile_is_applied_and_escaped() -> None:
    profile = ReportProfile(
        organisation_name="Agency <script>",
        client_name="Client & Co",
        consultant_name="Rafael <Admin>",
        accent_colour="#123ABC",
        introduction="Review <strong>carefully</strong>.",
        call_to_action_label="Book <now>",
        call_to_action_url="https://example.com/book?x=1&y=2",
        language="es",
        show_raw_evidence=False,
    )
    report = render_report(demo_assessment(), profile)

    assert "Agency &lt;script&gt; assessment report" in report
    assert "Client &amp; Co" in report
    assert "Rafael &lt;Admin&gt;" in report
    assert "Review &lt;strong&gt;carefully&lt;/strong&gt;." in report
    assert "Book &lt;now&gt;" in report
    assert "https://example.com/book?x=1&amp;y=2" in report
    assert "#123abc" in report
    assert "<html lang=\"es\">" in report
    assert "Evidence</th>" not in report
    assert "<pre>" not in report


def test_profile_rejects_unsafe_or_invalid_values() -> None:
    with pytest.raises(ValidationError):
        ReportProfile(accent_colour="red")
    with pytest.raises(ValidationError):
        ReportProfile(call_to_action_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        ReportProfile(language="fr")


def test_evidence_package_uses_the_same_custom_report() -> None:
    assessment = demo_assessment()
    profile = ReportProfile(organisation_name="Example Agency", show_raw_evidence=False)
    package = build_evidence_package(assessment, profile)

    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        report = archive.read("report.html").decode("utf-8")

    assert report == render_report(assessment, profile)
    assert "Example Agency assessment report" in report
    assert "Evidence</th>" not in report
