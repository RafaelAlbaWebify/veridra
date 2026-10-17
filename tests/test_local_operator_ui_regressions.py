"""Regressions for accepted local commercial operator UI and browser isolation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_workflow_step_labels_have_explicit_readable_color() -> None:
    source = (ROOT / "src/veridra/agency_workflow_web.py").read_text(
        encoding="utf-8"
    )
    assert ".local-home .flow-step strong{" in source
    assert "color:#17191c!important" in source


def test_commercial_launcher_gives_discovery_dedicated_profile() -> None:
    source = (ROOT / "scripts/windows/veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )
    assert "VERIDRA_BROWSER_PROFILE_DIRECTORY" in source
    assert "Join-Path $StateRoot 'browser-profile'" in source


def test_discovery_browser_subprocess_preserves_startup_diagnostics() -> None:
    source = (ROOT / "src/veridra/assisted_browser_provider.py").read_text(
        encoding="utf-8"
    )
    assert "discovery-browser-stderr.log" in source
    assert "stderr=stderr_log" in source
    assert "stderr=subprocess.DEVNULL" not in source


def test_isolated_acceptance_preserves_host_playwright_cache() -> None:
    source = (
        ROOT / "scripts/windows/VERIDRA_COMMERCIAL_HUMAN_ACCEPTANCE.ps1"
    ).read_text(encoding="utf-8")
    assert "PLAYWRIGHT_BROWSERS_PATH" in source
    assert "Join-Path $hostLocalAppData 'ms-playwright'" in source
    assert "$env:LOCALAPPDATA = $isolatedLocalAppData" in source
