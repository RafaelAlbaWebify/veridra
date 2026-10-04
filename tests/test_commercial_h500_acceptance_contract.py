from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts" / "windows" / "veridra-commercial-h500-acceptance.ps1"
).read_text(encoding="utf-8")
LAUNCHER = (ROOT / "VERIDRA_COMMERCIAL_H500_ACCEPTANCE.bat").read_text(
    encoding="utf-8"
)


def test_h500_acceptance_targets_real_local_commercial_runtime() -> None:
    assert "WEBIFY · VERIDRA LOCAL-AGENCY H-500 HUMAN ACCEPTANCE" in SCRIPT
    assert "http://127.0.0.1:8011/" in SCRIPT
    assert "$CommercialLauncher preflight" in SCRIPT
    assert "$CommercialLauncher start" in SCRIPT
    assert "$CommercialLauncher status" in SCRIPT
    assert "automated commercial acceptance does not satisfy this human H-500 gate" in SCRIPT


def test_h500_acceptance_covers_required_product_journey() -> None:
    for text in (
        "Client project and bounded audit",
        "White-label report / PDF",
        "Embedded lead generation",
        "Lead management / conversion",
        "Remediation / monitoring",
        "Restart / persistence",
        "Backup / independent copy / recovery",
        "Optional integrations and legacy-provider isolation",
        "Final H-500 decision",
    ):
        assert text in SCRIPT


def test_h500_acceptance_preserves_safety_boundaries() -> None:
    assert "synthetic/internal acceptance data only" in SCRIPT
    assert "no real outreach" in SCRIPT
    assert "no direct DB/store mutation" in SCRIPT
    assert "Do not configure a real notification recipient" in SCRIPT
    assert "No provider secret appears" in SCRIPT


def test_h500_launcher_invokes_dedicated_session_script() -> None:
    assert "veridra-commercial-h500-acceptance.ps1" in LAUNCHER
    assert "ExecutionPolicy Bypass" in LAUNCHER


def test_h500_rejects_saas_as_the_local_product_path() -> None:
    for text in (
        "Opening `/` enters the Webify local-agency console",
        "without a browser signup or login step",
        "`/signup`, `/login`, `/plans`, `/billing` and `/workspace` are not exposed",
        "not blocked by a VERIDRA plan, seat allowance or SaaS usage quota",
        "Normal Webify local startup does not require or load VERIDRA SaaS Stripe billing",
    ):
        assert text in SCRIPT
