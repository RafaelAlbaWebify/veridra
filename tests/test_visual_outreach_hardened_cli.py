from pathlib import Path

from veridra.visual_outreach_hardened_cli import (
    _commercial_overflow_reason,
    quality_rejection_reason,
)


def test_quality_gate_rejects_cloudflare_interstitial() -> None:
    assert (
        quality_rejection_reason(
            title="Just a moment...",
            visible_text="Checking your browser before accessing the site.",
            meaningful_elements=6,
        )
        == "challenge_or_interstitial"
    )


def test_quality_gate_rejects_effectively_blank_capture() -> None:
    assert (
        quality_rejection_reason(
            title="",
            visible_text="",
            meaningful_elements=1,
        )
        == "low_content_capture"
    )


def test_quality_gate_keeps_normal_business_page() -> None:
    assert (
        quality_rejection_reason(
            title="Phoenix Dental",
            visible_text=(
                "Welcome to Phoenix Dental. Book an appointment, meet our dentists, "
                "read about treatments, opening hours and contact information."
            ),
            meaningful_elements=12,
        )
        == ""
    )


def test_mobile_overflow_gate_rejects_minor_overflow() -> None:
    assert (
        _commercial_overflow_reason(
            {
                "issue_type": "mobile_overflow",
                "details": {"scrollWidth": 520, "viewportWidth": 390},
            }
        )
        == "minor_mobile_overflow"
    )


def test_mobile_overflow_gate_keeps_substantial_overflow() -> None:
    assert (
        _commercial_overflow_reason(
            {
                "issue_type": "mobile_overflow",
                "details": {"scrollWidth": 768, "viewportWidth": 390},
            }
        )
        == ""
    )


def test_visual_launcher_routes_through_hardened_module() -> None:
    content = Path("VERIDRA_VISUAL_EVIDENCE.bat").read_text(encoding="utf-8")
    assert "visual_outreach_hardened_cli" in content
