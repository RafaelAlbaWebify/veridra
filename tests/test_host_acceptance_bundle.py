from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "deployment"


def test_host_unit_installer_requires_real_env_and_enables_timers() -> None:
    script = (DEPLOYMENT / "install-host-units.sh").read_text(encoding="utf-8")

    assert "EUID" in script
    assert "deployment/veridra.env" not in script  # path assembled, not hard-coded secret content
    assert "chmod 600" in script
    assert "docker compose version" in script
    assert "systemctl enable --now veridra-worker.timer" in script
    assert "systemctl enable --now veridra-backup.timer" in script


def test_evidence_capture_never_dumps_runtime_environment() -> None:
    script = (DEPLOYMENT / "capture-host-evidence.sh").read_text(encoding="utf-8")

    assert "git_commit=" in script
    assert "docker compose" in script
    assert "health/live" in script
    assert "health/ready" in script
    assert "systemctl is-active veridra-worker.timer" in script
    assert "systemctl is-active veridra-backup.timer" in script
    assert "cat ${ENV_FILE}" not in script
    assert "env >" not in script
    assert "printenv" not in script
    assert "chmod 600" in script
