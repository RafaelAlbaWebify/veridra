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

def test_windows_isolated_localappdata_requires_browser_cache_override(
    tmp_path: Path,
) -> None:
    """Reproduce the regression using Playwright's real Windows registry."""
    import os
    import subprocess
    import sys

    import pytest

    if sys.platform != "win32":
        pytest.skip("Windows LOCALAPPDATA browser-registry contract")
    host_cache = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        or str(Path(os.environ["LOCALAPPDATA"]) / "ms-playwright")
    )
    assert host_cache.is_dir(), "Windows CI requires installed Chromium cache"
    isolated = tmp_path / "isolated-localappdata"
    isolated.mkdir()
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(isolated)
    env.pop("PLAYWRIGHT_BROWSERS_PATH", None)
    code = (
        "from playwright.sync_api import sync_playwright; "
        "p=sync_playwright().start(); "
        "print(p.chromium.executable_path); p.stop()"
    )
    missing = subprocess.check_output(
        [sys.executable, "-c", code], env=env, text=True
    ).strip()
    assert str(isolated).casefold() in missing.casefold()
    assert not Path(missing).is_file()

    env["PLAYWRIGHT_BROWSERS_PATH"] = str(host_cache)
    restored = subprocess.check_output(
        [sys.executable, "-c", code], env=env, text=True
    ).strip()
    assert str(host_cache).casefold() in restored.casefold()
    assert Path(restored).is_file()
