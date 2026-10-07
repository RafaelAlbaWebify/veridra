from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "tools" / "reboot_acceptance.py").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "VERIDRA_REBOOT_ACCEPTANCE.bat").read_text(encoding="utf-8")


def test_reboot_acceptance_is_two_phase_and_windows_only() -> None:
    assert 'choices=("prepare", "verify")' in RUNNER
    assert 'os.name != "nt"' in RUNNER
    assert "reboot-acceptance-marker.json" in RUNNER


def test_reboot_acceptance_records_machine_commit_and_boot_time() -> None:
    assert "socket.gethostname()" in RUNNER
    assert '"commit": _git(repo, "rev-parse", "HEAD")' in RUNNER
    assert "LastBootUpTime" in RUNNER
    assert '"boot_time_before"' in RUNNER
    assert '"boot_time_after"' in RUNNER


def test_reboot_verify_requires_real_boot_change_and_healthy_runtime() -> None:
    assert '"windows_boot_time_changed"' in RUNNER
    assert '"operator_start_after_reboot"' in RUNNER
    assert '"operator_status_after_reboot"' in RUNNER
    assert '"same_commit"' in RUNNER
    assert '"working_tree_clean"' in RUNNER


def test_reboot_launcher_exposes_prepare_and_verify() -> None:
    assert "prepare" in LAUNCHER
    assert "verify" in LAUNCHER
    assert "tools\\reboot_acceptance.py" in LAUNCHER
