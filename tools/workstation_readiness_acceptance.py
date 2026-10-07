from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _run(command: list[str], *, cwd: Path, timeout: int = 900) -> tuple[int, str]:
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No file matches {pattern!r} in {directory}")
    return matches[-1]


def _git(repo: Path, *args: str) -> str:
    code, output = _run(["git", "-C", str(repo), *args], cwd=repo, timeout=30)
    if code != 0:
        return "unavailable"
    return output.strip() or "(clean)"


def _parse_preflight(output: str) -> dict[str, Any] | None:
    for line in reversed([item.strip() for item in output.splitlines()]):
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "ready" in candidate and "status" in candidate:
            return candidate
    return None


def _powershell(repo: Path, command: str, *extra: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo / "scripts" / "windows" / "veridra-local.ps1"),
        command,
        *extra,
    ]


def run(second_copy_dir: Path) -> Path:
    if os.name != "nt":
        raise SystemExit("Workstation readiness acceptance must run on Windows.")

    repo = Path(__file__).resolve().parents[1]
    local_app_data = Path(os.environ["LOCALAPPDATA"]).resolve()
    state_root = (local_app_data / "Veridra").resolve()
    backup_root = state_root / "backups"

    second_copy_dir = second_copy_dir.expanduser().resolve()
    try:
        second_copy_dir.relative_to(state_root)
    except ValueError:
        pass
    else:
        raise SystemExit(
            "Second-copy directory must be outside the live VERIDRA state tree."
        )
    second_copy_dir.mkdir(parents=True, exist_ok=True)

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = downloads / f"VERIDRA_WORKSTATION_READINESS_{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output_zip = evidence_dir.with_suffix(".zip")

    report: dict[str, Any] = {
        "contract": "veridra_workstation_readiness_acceptance",
        "version": "1.0",
        "started_at": datetime.now(UTC).isoformat(),
        "passed": False,
        "workstation": {
            "computer_name": socket.gethostname(),
            "windows_user": os.environ.get("USERNAME", ""),
            "platform": platform.platform(),
        },
        "repository": {
            "path": str(repo),
            "branch": _git(repo, "branch", "--show-current"),
            "commit": _git(repo, "rev-parse", "HEAD"),
            "working_tree": _git(repo, "status", "--short"),
        },
        "second_copy_directory": str(second_copy_dir),
        "checks": {},
    }

    started_by_pack = False
    try:
        start_code, start_output = _run(
            _powershell(repo, "operator-start"),
            cwd=repo,
            timeout=300,
        )
        (evidence_dir / "operator-start.txt").write_text(
            start_output, encoding="utf-8", errors="replace"
        )
        report["checks"]["operator_start_exit_zero"] = start_code == 0
        started_by_pack = start_code == 0

        status_code, status_output = _run(
            _powershell(repo, "status"),
            cwd=repo,
            timeout=60,
        )
        (evidence_dir / "operator-status.txt").write_text(
            status_output, encoding="utf-8", errors="replace"
        )
        report["checks"]["operator_status_healthy"] = (
            status_code == 0
            and "Web: running PID" in status_output
            and "Monitoring: running PID" in status_output
        )

        preflight_code, preflight_output = _run(
            _powershell(repo, "operator-preflight"),
            cwd=repo,
            timeout=180,
        )
        (evidence_dir / "operator-preflight.txt").write_text(
            preflight_output, encoding="utf-8", errors="replace"
        )
        preflight = _parse_preflight(preflight_output)
        report["operator_preflight"] = {
            "exit_code": preflight_code,
            "result": preflight,
        }
        report["checks"]["operator_preflight_ready"] = bool(
            preflight and preflight.get("ready") is True
        )

        diagnostics_code, diagnostics_output = _run(
            _powershell(repo, "diagnostics"),
            cwd=repo,
            timeout=60,
        )
        (evidence_dir / "diagnostics-console.txt").write_text(
            diagnostics_output, encoding="utf-8", errors="replace"
        )
        report["checks"]["diagnostics_created"] = diagnostics_code == 0

        before = set(backup_root.glob("VERIDRA_BACKUP_*.zip")) if backup_root.exists() else set()
        backup_code, backup_output = _run(
            _powershell(repo, "operator-backup"),
            cwd=repo,
            timeout=300,
        )
        (evidence_dir / "operator-backup.txt").write_text(
            backup_output, encoding="utf-8", errors="replace"
        )
        after = set(backup_root.glob("VERIDRA_BACKUP_*.zip")) if backup_root.exists() else set()
        created = sorted(after - before, key=lambda path: path.stat().st_mtime)
        backup = created[-1] if created else _latest(backup_root, "VERIDRA_BACKUP_*.zip")
        report["checks"]["verified_backup_created"] = backup_code == 0 and backup.is_file()

        source_hash = _sha256(backup)
        copied_backup = second_copy_dir / backup.name
        shutil.copy2(backup, copied_backup)
        copied_hash = _sha256(copied_backup)
        report["backup"] = {
            "source": str(backup),
            "source_sha256": source_hash,
            "second_copy": str(copied_backup),
            "second_copy_sha256": copied_hash,
        }
        report["checks"]["independent_second_copy_hash_matches"] = (
            copied_backup.is_file() and source_hash == copied_hash
        )

        recovery_code, recovery_output = _run(
            _powershell(
                repo,
                "operator-recovery-test",
                "-BackupPath",
                str(copied_backup),
            ),
            cwd=repo,
            timeout=300,
        )
        (evidence_dir / "operator-recovery-test.txt").write_text(
            recovery_output, encoding="utf-8", errors="replace"
        )
        report["checks"]["representative_isolated_recovery_passed"] = (
            recovery_code == 0
            and "Isolated recovery PASS" in recovery_output
            and "recovery_readiness=PASS" in recovery_output
        )

        report["passed"] = all(bool(value) for value in report["checks"].values())
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["runtime_started_by_pack"] = started_by_pack
        (evidence_dir / "workstation-readiness-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(evidence_dir.iterdir()):
                archive.write(path, arcname=path.name)

    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"Evidence ZIP: {output_zip}")
    if not report["passed"]:
        raise SystemExit(1)
    return output_zip


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create #296 Windows-workstation evidence: operator runtime, preflight, "
            "backup, independent second copy and representative isolated recovery."
        )
    )
    parser.add_argument(
        "--second-copy-dir",
        required=True,
        type=Path,
        help=(
            "Operator-controlled directory outside %LOCALAPPDATA%\\Veridra used "
            "for the independent verified backup copy."
        ),
    )
    args = parser.parse_args(argv)
    run(args.second_copy_dir)


if __name__ == "__main__":
    main()
