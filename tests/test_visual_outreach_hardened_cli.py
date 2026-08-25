from pathlib import Path

from veridra.visual_outreach_hardened_cli import quality_rejection_reason


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


def test_visual_launcher_routes_through_hardened_module() -> None:
    content = Path("VERIDRA_VISUAL_EVIDENCE.bat").read_text(encoding="utf-8")
    assert "visual_outreach_hardened_cli" in content
