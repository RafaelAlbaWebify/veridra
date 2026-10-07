from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "tools" / "workstation_readiness_acceptance.py").read_text(
    encoding="utf-8"
)
LAUNCHER = (ROOT / "VERIDRA_WORKSTATION_READINESS.bat").read_text(
    encoding="utf-8"
)


def test_workstation_readiness_records_exact_machine_and_repository_state() -> None:
    assert '"computer_name": socket.gethostname()' in RUNNER
    assert '"platform": platform.platform()' in RUNNER
    assert '"commit": commit' in RUNNER
    assert '"repository_working_tree_clean"' in RUNNER


def test_workstation_readiness_requires_distinct_second_copy_storage() -> None:
    assert "different Windows drive or UNC" in RUNNER
    assert "storage target from the live VERIDRA state." in RUNNER
    assert "copy_drive == live_drive" in RUNNER
    assert '"second_copy_uses_distinct_storage_root"' in RUNNER
    assert '"second_copy_hash_matches"' in RUNNER


def test_workstation_readiness_runs_operator_preflight_and_browser_acceptance() -> None:
    assert '"operator-preflight"' in RUNNER
    assert "VERIDRA_OPERATOR_E2E_ACCEPTANCE.bat" in RUNNER
    assert '"operator_browser_acceptance_report_passed"' in RUNNER


def test_workstation_readiness_audits_sensitive_state_acl() -> None:
    assert "S-1-1-0" in RUNNER
    assert "S-1-5-11" in RUNNER
    assert "S-1-5-32-545" in RUNNER
    assert '"operator_state_not_broadly_writable"' in RUNNER
    assert "operator-state-acl.json" in RUNNER


def test_workstation_readiness_proves_backup_and_representative_recovery() -> None:
    assert '"operator-backup"' in RUNNER
    assert '"operator-recovery-test"' in RUNNER
    assert "recovery_readiness=PASS" in RUNNER
    assert '"representative_isolated_recovery_passed"' in RUNNER


def test_windows_launcher_requires_second_copy_directory() -> None:
    assert "SECOND_COPY_DIRECTORY" in LAUNCHER
    assert "workstation_readiness_acceptance.py" in LAUNCHER
    assert "--second-copy-dir" in LAUNCHER
