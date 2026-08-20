from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "tools" / "commercial_acceptance.py").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "VERIDRA_COMMERCIAL_ACCEPTANCE.bat").read_text(encoding="utf-8")


def test_runner_uses_isolated_composed_runtime() -> None:
    assert '"-m", "veridra.runtime"' in RUNNER
    assert "TemporaryDirectory" in RUNNER
    assert '"VERIDRA_IDENTITY_DB"' in RUNNER
    assert '"VERIDRA_TENANT_DATA_ROOT"' in RUNNER
    assert '"VERIDRA_TRUSTED_ORIGIN"' in RUNNER


def test_runner_drives_commercial_agency_journey() -> None:
    assert 'page.goto(f"{base_url}/onboarding"' in RUNNER
    assert 'page.wait_for_url(f"{base_url}/agency")' in RUNNER
    assert 'page.goto(f"{base_url}/workspace"' in RUNNER
    assert 'select_option("professional")' in RUNNER
    assert '"Preview plan"' in RUNNER
    assert '"Apply local policy"' in RUNNER
    assert 'checks["professional_plan_enabled"]' in RUNNER
    assert '"Create client project"' in RUNNER
    assert '"Prepare branded report"' in RUNNER
    assert '"Create or change report profile"' in RUNNER
    assert '"Create and apply profile"' in RUNNER
    assert '"Preview branded HTML"' in RUNNER
    assert '"Download PDF"' in RUNNER
    assert '"Enable monitoring"' in RUNNER
    assert '"standard"' in RUNNER


def test_runner_verifies_white_label_report_identity() -> None:
    assert 'ACCEPTANCE_BRAND = "Acceptance Agency"' in RUNNER
    assert 'ACCEPTANCE_COVER_TITLE = "Demo SMB Website Review"' in RUNNER
    assert (
        'ACCEPTANCE_SUMMARY = "Acceptance-authored executive summary."' in RUNNER
    )
    assert 'checks["profile_created"]' in RUNNER
    assert 'checks["html_cover_title_visible"]' in RUNNER
    assert 'checks["html_summary_visible"]' in RUNNER
    assert 'checks["html_veridra_not_visible"]' in RUNNER
    assert 'checks["pdf_filename_branded"]' in RUNNER
    assert 'checks["pdf_signature_valid"]' in RUNNER
    assert 'filename.startswith("Demo-SMB-Website-Review-")' in RUNNER
    assert 'not filename.startswith("Veridra-")' in RUNNER
    assert 'page.expect_download(timeout=60_000)' in RUNNER
    assert 'pdf_content.startswith(b"%PDF-")' in RUNNER


def test_runner_captures_reviewable_evidence() -> None:
    assert "page.screenshot" in RUNNER
    assert "page.content()" in RUNNER
    assert '"console_errors"' in RUNNER
    assert '"request_failures"' in RUNNER
    assert '"checks": {}' in RUNNER
    assert '"commercial-acceptance.json"' in RUNNER
    assert 'report["pdf"]' in RUNNER
    assert "download.save_as(pdf_path)" in RUNNER
    assert "shutil.make_archive" in RUNNER


def test_real_target_mode_is_explicit_and_optional() -> None:
    assert 'parser.add_argument(' in RUNNER
    assert '"--target"' in RUNNER
    assert '"mode": "real-target" if target else "isolated-demo"' in RUNNER


def test_windows_launcher_requires_existing_setup() -> None:
    assert '.venv\\Scripts\\python.exe' in LAUNCHER
    assert "VERIDRA_SETUP.bat" in LAUNCHER
    assert "tools\\commercial_acceptance.py %*" in LAUNCHER
