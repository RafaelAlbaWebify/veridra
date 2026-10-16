"""Contract tests for one-command combined operator rehearsal."""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "webify_engagement_review.py"
SPEC = importlib.util.spec_from_file_location("webify_engagement_review", MODULE)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_latest_after_ignores_stale_evidence(tmp_path: Path) -> None:
    old = tmp_path / "VERIDRA_LIVE_AUDIT_REVIEW_old.zip"
    old.write_bytes(b"old")
    assert runner._latest_after(tmp_path, "VERIDRA_LIVE_AUDIT_REVIEW_", old.stat().st_mtime_ns + 1) is None
    assert runner._latest_after(tmp_path, "VERIDRA_LIVE_AUDIT_REVIEW_", 0) == old


def test_combined_review_keeps_live_and_synthetic_separate(tmp_path: Path, monkeypatch) -> None:
    audit = tmp_path / "VERIDRA_LIVE_AUDIT_REVIEW_new.zip"
    lifecycle = tmp_path / "VERIDRA_OPERATOR_E2E_ACCEPTANCE_new.zip"
    audit.write_bytes(b"public")
    lifecycle.write_bytes(b"synthetic")
    events: list[str] = []

    def run(_repo: Path, command: list[str], _log: Path) -> int:
        events.append("public" if "LIVE_AUDIT" in command[2] else "synthetic")
        return 0

    monkeypatch.setattr(runner, "_run", run)
    monkeypatch.setattr(runner, "_latest_after", lambda folder, prefix, started: (
        audit if "LIVE_AUDIT" in prefix else lifecycle
    ))
    monkeypatch.setattr(sys, "argv", [
        "webify_engagement_review.py", "--url", "https://basecamp.com/",
        "--output", str(tmp_path),
    ])
    assert runner.main() == 0
    assert events == ["public", "synthetic"]
    combined = list(tmp_path.glob("VERIDRA_WEBIFY_ENGAGEMENT_REVIEW_*.zip"))
    assert len(combined) == 1
    with zipfile.ZipFile(combined[0]) as archive:
        summary = json.loads(archive.read("engagement-summary.json"))
        assert summary["passed"] is True
        assert summary["commercial_quality_accepted"] is False
        assert summary["data_isolation"].startswith("live read-only")
        assert len([p for p in archive.namelist() if p.endswith(".zip")]) == 2


def test_failed_audit_stops_before_synthetic_lifecycle(tmp_path: Path, monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(runner, "_run", lambda repo, command, log: events.append("audit") or 1)
    monkeypatch.setattr(runner, "_latest_after", lambda *args: None)
    monkeypatch.setattr(sys, "argv", [
        "webify_engagement_review.py", "--output", str(tmp_path),
    ])
    assert runner.main() == 1
    assert events == ["audit"]
