from __future__ import annotations

import runpy
import sqlite3
from pathlib import Path

_module = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "tools" / "webify_data_inventory.py")
)
inventory = _module["inventory"]


def test_inventory_is_read_only_and_counts_historical_saas_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "identity.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE users (id TEXT)")
        connection.execute("CREATE TABLE tenants (id TEXT)")
        connection.execute("INSERT INTO users VALUES ('owner')")
        connection.execute("INSERT INTO tenants VALUES ('tenant')")
    root = tmp_path / "tenants"
    tenant = root / ("a" * 24)
    workspace = tenant / "workspace"
    (workspace / "billing").mkdir(parents=True)
    (workspace / "plan-changes").mkdir()
    (workspace / "workspace.json").write_text("{}", encoding="utf-8")
    (workspace / "billing" / "stripe.json").write_text("{}", encoding="utf-8")
    (workspace / "plan-changes" / "old.json").write_text("{}", encoding="utf-8")
    project_dir = tenant / "projects" / "project01" / "assessments"
    project_dir.mkdir(parents=True)
    (tenant / "projects" / "project01.json").write_text("{}", encoding="utf-8")
    (project_dir / "audit.json").write_text("{}", encoding="utf-8")
    files_before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    report = inventory(database, root)

    assert report["identity"] == {
        "state": "readable",
        "tables": {"users": 1, "tenants": 1},
        "integrity": "ok",
    }
    assert report["tenant_directories"] == 1
    assert report["projects"] == 1
    assert report["assessments"] == 1
    assert report["legacy_workspace_configs"] == 1
    assert report["legacy_plan_events"] == 1
    assert report["legacy_saas_stripe_bindings"] == 1
    assert files_before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_missing_identity_and_tenant_root_are_reported_without_creating_files(
    tmp_path: Path,
) -> None:
    report = inventory(tmp_path / "missing.sqlite3", tmp_path / "missing-tenants")
    assert report["identity"]["state"] == "missing"
    assert report["tenant_root_exists"] is False
    assert report["tenant_directories"] == 0
    assert sorted(tmp_path.iterdir()) == []


def test_inventory_rejects_wal_snapshot_without_reading_stale_identity_counts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "identity.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE users (id TEXT)")
        connection.execute("CREATE TABLE tenants (id TEXT)")
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"uncheckpointed WAL sentinel")
    try:
        report = inventory(database, tmp_path / "tenants")
        assert report["identity"]["state"] == "unsafe_snapshot"
        assert report["identity"]["tables"] == {}
        assert report["identity"]["integrity"] == "not_checked"
        assert wal.read_bytes() == b"uncheckpointed WAL sentinel"
    finally:
        wal.unlink()
