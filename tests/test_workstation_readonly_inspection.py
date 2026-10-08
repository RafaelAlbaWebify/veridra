from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from workstation_readonly_inspection import inspect  # type: ignore[import-not-found]  # noqa: E402


def test_inspection_is_read_only_and_records_evidence(tmp_path: Path) -> None:
    root = tmp_path / "Veridra"
    for name in ("data", "runtime", "config"):
        (root / name).mkdir(parents=True, exist_ok=True)

    def git(_repo: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "abc123"
        if args == ("branch", "--show-current"):
            return "main"
        return "(clean)"

    with (
        patch("workstation_readonly_inspection._git", side_effect=git),
        patch("workstation_readonly_inspection._run", return_value=(
            0, "[Veridra] Web: running PID 12\n[Veridra] Monitoring: running PID 13",
        )) as runner,
        patch("workstation_readonly_inspection._audit_acl", return_value=(
            0, json.dumps({"passed": True, "risky_write_entries": []}),
        )),
    ):
        output, report = inspect(tmp_path, root, tmp_path / "Downloads")

    assert report["passed"] is True
    assert report["service_changes_performed"] is False
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["checks"] == report["checks"]
    assert runner.call_count == 1
    assert "status" in runner.call_args.args[0]
    assert "operator-restart" not in str(runner.call_args)


def test_missing_state_paths_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "Veridra"
    root.mkdir()
    with (
        patch("workstation_readonly_inspection._git", return_value="(clean)"),
        patch("workstation_readonly_inspection._run", return_value=(1, "")),
        patch(
            "workstation_readonly_inspection._audit_acl",
            return_value=(0, '{"passed": true}'),
        ) as acl,
    ):
        _, report = inspect(tmp_path, root, tmp_path / "Downloads")

    assert report["passed"] is False
    assert report["checks"]["required_state_paths_exist"] is False
    acl.assert_called_once()
