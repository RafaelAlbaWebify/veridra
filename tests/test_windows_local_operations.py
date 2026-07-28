from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LAUNCHERS = {
    "VERIDRA_SETUP.bat": "setup",
    "VERIDRA_START.bat": "start",
    "VERIDRA_STOP.bat": "stop",
    "VERIDRA_RESTART.bat": "restart",
    "VERIDRA_STATUS.bat": "status",
    "VERIDRA_OPEN.bat": "open",
    "VERIDRA_TEST.bat": "test",
    "VERIDRA_BACKUP.bat": "backup",
    "VERIDRA_RESTORE.bat": "restore",
    "VERIDRA_DIAGNOSTICS.bat": "diagnostics",
    "VERIDRA_CREATE_SHORTCUT.bat": "create-shortcut",
}


def test_windows_launchers_are_thin_wrappers() -> None:
    for name, command in EXPECTED_LAUNCHERS.items():
        content = (ROOT / name).read_text(encoding="utf-8")
        assert "scripts\\windows\\veridra-local.ps1" in content
        assert f'" {command}' in content
        assert "ExecutionPolicy Bypass" in content


def test_windows_operations_script_has_safe_local_boundaries() -> None:
    content = (ROOT / "scripts/windows/veridra-local.ps1").read_text(encoding="utf-8")
    assert "LOCALAPPDATA" in content
    assert "127.0.0.1" in content
    assert "VERIDRA_TENANT_DATA_ROOT" in content
    assert "Preview only" in content
    assert "create-shortcut" in content
    assert "Get-NetTCPConnection" in content


def test_runtime_module_can_be_launched_with_python_m() -> None:
    content = (ROOT / "src/veridra/runtime.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in content
    assert "main()" in content
