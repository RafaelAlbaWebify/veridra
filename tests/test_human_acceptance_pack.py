from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_human_acceptance_launcher_uses_supported_operator_runtime() -> None:
    launcher = (ROOT / "VERIDRA_HUMAN_ACCEPTANCE.bat").read_text(encoding="utf-8")
    script = (ROOT / "scripts/windows/veridra-human-acceptance.ps1").read_text(
        encoding="utf-8"
    )

    assert "veridra-human-acceptance.ps1" in launcher
    assert "veridra-local.ps1" in script
    assert "open" in script
    assert "diagnostics" in script


def test_human_acceptance_pack_preserves_manual_and_no_outreach_boundary() -> None:
    script = (ROOT / "scripts/windows/veridra-human-acceptance.ps1").read_text(
        encoding="utf-8"
    )
    guide = (ROOT / "docs/HUMAN_OPERATOR_ACCEPTANCE.md").read_text(encoding="utf-8")

    for expected in (
        "synthetic/internal data only",
        "no real outreach",
        "automated E2E does not complete this human gate",
    ):
        assert expected.lower() in script.lower()

    assert "Automated Playwright/CI is supporting evidence only" in guide
    assert "Do not work around confusing or missing UI" in guide


def test_human_acceptance_checklist_covers_new_product_surfaces() -> None:
    script = (ROOT / "scripts/windows/veridra-human-acceptance.ps1").read_text(
        encoding="utf-8"
    )

    for expected in (
        "Review Intelligence",
        "AI review exchange",
        "Progress / Changes",
        "Backup / restore",
        "Whole-app UX judgment",
        "Overall workflow is acceptable for real-world validation",
    ):
        assert expected in script
