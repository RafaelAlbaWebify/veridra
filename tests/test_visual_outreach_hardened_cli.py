import json
import zipfile
from pathlib import Path

import pytest

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


def test_empty_evidence_repackage_does_not_start_chromium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from veridra import visual_outreach_hardened_cli as module

    output = tmp_path / "evidence.zip"
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr(
            "visual_evidence.json",
            json.dumps([{"business_name": "Synthetic Clinic", "evidence": []}]),
        )

    def forbidden_browser() -> None:
        raise AssertionError("Chromium must not launch for empty visual evidence")

    monkeypatch.setattr(module, "sync_playwright", forbidden_browser)
    result = module._rewrite_zip(output=output, country_code="IE", timeout_ms=20000)
    assert result["fresh_broken_links_verified"] == 0
    with zipfile.ZipFile(output) as archive:
        rows = json.loads(archive.read("visual_evidence.json"))
        assert rows[0]["screenshot_ready_count"] == 0
        assert rows[0]["evidence"] == []
        assert json.loads(archive.read("manifest.json"))["schema_version"] == 4
