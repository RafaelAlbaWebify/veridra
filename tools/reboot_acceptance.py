from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _run(command: list[str], *, cwd: Path, timeout: int = 120) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout


def _git(repo: Path, *args: str) -> str:
    code, output = _run(["git", "-C", str(repo), *args], cwd=repo, timeout=30)
    return output.strip() if code == 0 else "unavailable"


def _boot_time(repo: Path) -> str:
    script = (
        "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"
        ".ToUniversalTime().ToString('o')"
    )
    code, output = _run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        cwd=repo,
        timeout=30,
    )
    if code != 0 or not output.strip():
        raise RuntimeError("Unable to read Windows boot time.")
    return output.strip().splitlines()[-1].strip()


def _launcher(repo: Path, command: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo / "scripts" / "windows" / "veridra-local.ps1"),
        command,
    ]


def _marker_path() -> Path:
    return (
        Path(os.environ["LOCALAPPDATA"])
        / "Veridra"
        / "runtime"
        / "reboot-acceptance-marker.json"
    )


def prepare() -> Path:
    if os.name != "nt":
        raise SystemExit("Reboot acceptance must run on Windows.")

    repo = Path(__file__).resolve().parents[1]
    marker = _marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)

    start_code, start_output = _run(
        _launcher(repo, "operator-start"),
        cwd=repo,
        timeout=300,
    )
    status_code, status_output = _run(
        _launcher(repo, "status"),
        cwd=repo,
        timeout=60,
    )
    if (
        start_code != 0
        or status_code != 0
        or "Web: running PID" not in status_output
        or "Monitoring: running PID" not in status_output
    ):
        print(start_output)
        print(status_output)
        raise SystemExit("Operator runtime is not healthy before reboot.")

    working_tree = _git(repo, "status", "--short")
    if working_tree:
        raise SystemExit(
            "Repository working tree must be clean before reboot acceptance."
        )

    payload: dict[str, Any] = {
        "contract": "veridra_reboot_acceptance",
        "version": "1.0",
        "prepared_at": datetime.now(UTC).isoformat(),
        "computer_name": socket.gethostname(),
        "windows_user": os.environ.get("USERNAME", ""),
        "repository": str(repo),
        "branch": _git(repo, "branch", "--show-current"),
        "commit": _git(repo, "rev-parse", "HEAD"),
        "boot_time_before": _boot_time(repo),
        "status_before": status_output,
    }
    marker.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Reboot acceptance prepared: {marker}")
    print("Restart Windows, then run: VERIDRA_REBOOT_ACCEPTANCE.bat verify")
    return marker


def verify() -> Path:
    if os.name != "nt":
        raise SystemExit("Reboot acceptance must run on Windows.")

    repo = Path(__file__).resolve().parents[1]
    marker = _marker_path()
    if not marker.is_file():
        raise SystemExit(
            "No reboot acceptance marker exists. Run prepare before rebooting Windows."
        )

    before = json.loads(marker.read_text(encoding="utf-8"))
    if before.get("contract") != "veridra_reboot_acceptance":
        raise SystemExit("Reboot acceptance marker has an unexpected contract.")

    current_machine = socket.gethostname()
    current_commit = _git(repo, "rev-parse", "HEAD")
    current_tree = _git(repo, "status", "--short")
    boot_after = _boot_time(repo)

    checks = {
        "same_machine": before.get("computer_name") == current_machine,
        "same_commit": before.get("commit") == current_commit,
        "working_tree_clean": current_tree == "",
        "windows_boot_time_changed": before.get("boot_time_before") != boot_after,
    }

    start_code, start_output = _run(
        _launcher(repo, "operator-start"),
        cwd=repo,
        timeout=300,
    )
    status_code, status_output = _run(
        _launcher(repo, "status"),
        cwd=repo,
        timeout=60,
    )
    checks["operator_start_after_reboot"] = start_code == 0
    checks["operator_status_after_reboot"] = (
        status_code == 0
        and "Web: running PID" in status_output
        and "Monitoring: running PID" in status_output
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = (
        Path.home()
        / "Downloads"
        / f"VERIDRA_REBOOT_ACCEPTANCE_{stamp}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "contract": "veridra_reboot_acceptance",
        "version": "1.0",
        "prepared_at": before.get("prepared_at"),
        "verified_at": datetime.now(UTC).isoformat(),
        "computer_name": current_machine,
        "windows_user": os.environ.get("USERNAME", ""),
        "repository": str(repo),
        "branch": _git(repo, "branch", "--show-current"),
        "commit": current_commit,
        "boot_time_before": before.get("boot_time_before"),
        "boot_time_after": boot_after,
        "checks": checks,
        "status_after": status_output,
        "start_output": start_output,
        "passed": all(checks.values()),
    }
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    if report["passed"]:
        marker.unlink(missing_ok=True)
        print(f"Reboot acceptance PASS: {output}")
        return output

    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"Reboot acceptance FAIL evidence: {output}")
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Prepare or verify the #296 Windows reboot acceptance gate."
    )
    parser.add_argument("phase", choices=("prepare", "verify"))
    args = parser.parse_args(argv)
    if args.phase == "prepare":
        prepare()
    else:
        verify()


if __name__ == "__main__":
    main()
