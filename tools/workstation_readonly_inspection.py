from __future__ import annotations

import json
import os
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from workstation_readiness_acceptance import _audit_acl, _git, _powershell, _run


def inspect(repo: Path, state_root: Path, downloads: Path) -> tuple[Path, dict[str, Any]]:
    """Collect non-disruptive workstation evidence without changing VERIDRA processes."""
    paths = [
        state_root,
        state_root / "data",
        state_root / "runtime",
        state_root / "config",
    ]
    status_code, status_output = _run(_powershell(repo, "status"), cwd=repo, timeout=60)

    existing = [path for path in paths if path.exists()]
    missing = [str(path) for path in paths if not path.exists()]
    if existing:
        acl_code, acl_output = _audit_acl(existing, cwd=repo)
        try:
            acl_result = json.loads(acl_output)
        except json.JSONDecodeError:
            acl_result = {"error": "Unable to parse ACL result"}
    else:
        acl_code = 1
        acl_result = {"error": "No state directories found"}

    commit = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")
    tree = _git(repo, "status", "--short")
    checks = {
        "commit_recorded": commit not in {"", "unavailable"},
        "working_tree_clean": tree == "(clean)",
        "operator_web_running": status_code == 0 and "Web: running PID" in status_output,
        "operator_monitoring_running": status_code == 0
        and "Monitoring: running PID" in status_output,
        "required_state_paths_exist": not missing,
        "state_acl_not_broadly_writable": acl_code == 0 and not missing,
    }
    report: dict[str, Any] = {
        "contract": "veridra_workstation_readonly_inspection",
        "version": "1.0",
        "inspected_at": datetime.now(UTC).isoformat(),
        "computer_name": socket.gethostname(),
        "windows_user": os.environ.get("USERNAME", ""),
        "repository": {"path": str(repo), "branch": branch, "commit": commit},
        "checks": checks,
        "missing_state_paths": missing,
        "acl": acl_result,
        "passed": all(checks.values()),
        "service_changes_performed": False,
    }
    downloads.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = downloads / f"VERIDRA_WORKSTATION_READONLY_{stamp}.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return output, report


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Windows workstation inspection must run on Windows.")
    repo = Path(__file__).resolve().parents[1]
    state_root = Path(os.environ["LOCALAPPDATA"]).resolve() / "Veridra"
    output, report = inspect(repo, state_root, Path.home() / "Downloads")
    print(f"Read-only workstation evidence: {output}")
    print(json.dumps(report["checks"], indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
