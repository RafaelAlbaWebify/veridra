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
    "VERIDRA_OPERATOR_START.bat": "operator-start",
    "VERIDRA_OPERATOR_OPEN.bat": "operator-open",
    "VERIDRA_OPERATOR_RESTART.bat": "operator-restart",
    "VERIDRA_OPERATOR_PREFLIGHT.bat": "operator-preflight",
    "VERIDRA_RECOVERY_TEST.bat": "recovery-test",
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


def test_windows_local_port_is_configurable_and_defaults_away_from_8000() -> None:
    content = (ROOT / "scripts/windows/veridra-local.ps1").read_text(encoding="utf-8")
    assert "[int]$Port = 8010" in content
    assert "VERIDRA_LOCAL_PORT" in content
    assert '$env:VERIDRA_BIND_PORT = "$Port"' in content
    assert '$Url = "http://127.0.0.1:$Port/"' in content


def test_windows_start_uses_separate_stdout_and_stderr_logs() -> None:
    content = (ROOT / "scripts/windows/veridra-local.ps1").read_text(encoding="utf-8")
    assert "veridra.stdout.log" in content
    assert "veridra.stderr.log" in content
    assert "-RedirectStandardOutput $StdoutLogFile" in content
    assert "-RedirectStandardError $StderrLogFile" in content
    assert "-RedirectStandardOutput $LogFile -RedirectStandardError $LogFile" not in content


def test_runtime_module_can_be_launched_with_python_m() -> None:
    content = (ROOT / "src/veridra/runtime.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in content
    assert "main()" in content


def test_windows_operator_mode_is_explicit_and_loopback_only() -> None:
    content = (ROOT / "scripts/windows/veridra-local.ps1").read_text(encoding="utf-8")
    assert "operator-start" in content
    assert "operator-restart" in content
    assert "operator-preflight" in content
    assert "$script:RuntimeProfile = 'operator'" in content
    assert '$env:VERIDRA_BIND_HOST = \'127.0.0.1\'' in content
    assert '$Url = "http://127.0.0.1:$Port/"' in content


def test_windows_backup_uses_verified_backup_cli() -> None:
    content = (ROOT / "scripts/windows/veridra-local.ps1").read_text(encoding="utf-8")
    assert "veridra.backup_restore_cli backup" in content
    assert "--confirm-quiesced" in content
    assert "Verified backup created" in content


def test_windows_recovery_test_restores_to_isolated_root() -> None:
    content = (ROOT / "scripts/windows/veridra-local.ps1").read_text(encoding="utf-8")
    assert "recovery-test-" in content
    assert "veridra.backup_restore_cli restore" in content
    assert "Isolated recovery PASS" in content
    assert "PRAGMA quick_check" in content


def test_windows_restore_uses_verified_restore_cli() -> None:
    content = (ROOT / "scripts/windows/veridra-local.ps1").read_text(encoding="utf-8")
    assert "veridra.backup_restore_cli restore" in content
    assert "--replace-existing" in content
    assert "Pre-restore safety backup failed; restore aborted." in content
    assert "Restore applied and verified." in content
