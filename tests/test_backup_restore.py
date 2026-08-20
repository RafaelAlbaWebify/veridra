from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.backup_restore import (
    BackupRestoreError,
    create_backup,
    restore_backup,
)

NOW = datetime(2026, 8, 20, 16, 15, tzinfo=UTC)


def _identity(path: Path, value: str = "original") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO users VALUES ('user-1', ?)", (value,))


def _read_identity(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT value FROM users WHERE id = 'user-1'").fetchone()
    assert row is not None
    return str(row[0])


def _source_state(tmp_path: Path) -> tuple[Path, Path]:
    identity = tmp_path / "source" / "identity" / "identity.sqlite3"
    tenants = tmp_path / "source" / "tenants"
    _identity(identity)
    email = identity.parent / "identity-email-deliveries" / "attempt.json"
    email.parent.mkdir(parents=True)
    email.write_text('{"status":"delivered"}', encoding="utf-8")
    project = tenants / ("a" * 24) / "projects" / "project.json"
    project.parent.mkdir(parents=True)
    project.write_text('{"name":"Example"}', encoding="utf-8")
    monitoring = tenants / "monitoring-jobs.sqlite3"
    with sqlite3.connect(monitoring) as connection:
        connection.execute("CREATE TABLE monitoring_jobs (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO monitoring_jobs VALUES ('job-1')")
    return identity, tenants


def test_backup_requires_explicit_quiescence(tmp_path: Path) -> None:
    identity, tenants = _source_state(tmp_path)

    with pytest.raises(BackupRestoreError, match="quiesced"):
        create_backup(
            identity_database=identity,
            tenant_data_root=tenants,
            output=tmp_path / "backup.zip",
            confirm_quiesced=False,
        )


def test_backup_restore_round_trip_includes_all_durable_roots(tmp_path: Path) -> None:
    identity, tenants = _source_state(tmp_path)
    archive = tmp_path / "backups" / "snapshot.zip"

    backup = create_backup(
        identity_database=identity,
        tenant_data_root=tenants,
        output=archive,
        confirm_quiesced=True,
        now=NOW,
    )

    assert backup.archive == archive.resolve()
    assert backup.manifest.consistency == "operator_quiesced"
    members = {entry.path for entry in backup.manifest.files}
    assert "identity/identity.sqlite3" in members
    assert "identity/identity-email-deliveries/attempt.json" in members
    assert f"tenants/{'a' * 24}/projects/project.json" in members
    assert "tenants/monitoring-jobs.sqlite3" in members

    restored_identity = tmp_path / "restored" / "identity" / "identity.sqlite3"
    restored_tenants = tmp_path / "restored" / "tenants"
    result = restore_backup(
        archive=archive,
        identity_database=restored_identity,
        tenant_data_root=restored_tenants,
        confirm_quiesced=True,
    )

    assert result.restored_files == len(backup.manifest.files)
    assert _read_identity(restored_identity) == "original"
    assert (
        restored_identity.parent / "identity-email-deliveries" / "attempt.json"
    ).read_text(encoding="utf-8") == '{"status":"delivered"}'
    assert (
        restored_tenants / ("a" * 24) / "projects" / "project.json"
    ).read_text(encoding="utf-8") == '{"name":"Example"}'
    with sqlite3.connect(restored_tenants / "monitoring-jobs.sqlite3") as connection:
        assert connection.execute("SELECT id FROM monitoring_jobs").fetchone() == ("job-1",)


def test_restore_refuses_existing_state_without_explicit_replace(tmp_path: Path) -> None:
    identity, tenants = _source_state(tmp_path)
    archive = tmp_path / "snapshot.zip"
    create_backup(
        identity_database=identity,
        tenant_data_root=tenants,
        output=archive,
        confirm_quiesced=True,
    )

    target_identity = tmp_path / "target" / "identity" / "identity.sqlite3"
    target_tenants = tmp_path / "target" / "tenants"
    _identity(target_identity, "keep")
    target_tenants.mkdir(parents=True)
    (target_tenants / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(BackupRestoreError, match="already contain durable state"):
        restore_backup(
            archive=archive,
            identity_database=target_identity,
            tenant_data_root=target_tenants,
            confirm_quiesced=True,
        )

    assert _read_identity(target_identity) == "keep"
    assert (target_tenants / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_explicit_replace_restores_snapshot_over_existing_state(tmp_path: Path) -> None:
    identity, tenants = _source_state(tmp_path)
    archive = tmp_path / "snapshot.zip"
    create_backup(
        identity_database=identity,
        tenant_data_root=tenants,
        output=archive,
        confirm_quiesced=True,
    )

    target_identity = tmp_path / "target" / "identity" / "identity.sqlite3"
    target_tenants = tmp_path / "target" / "tenants"
    _identity(target_identity, "obsolete")
    target_tenants.mkdir(parents=True)
    (target_tenants / "obsolete.txt").write_text("obsolete", encoding="utf-8")

    restore_backup(
        archive=archive,
        identity_database=target_identity,
        tenant_data_root=target_tenants,
        confirm_quiesced=True,
        replace_existing=True,
    )

    assert _read_identity(target_identity) == "original"
    assert not (target_tenants / "obsolete.txt").exists()
    assert (target_tenants / "monitoring-jobs.sqlite3").is_file()


def test_restore_rejects_manifest_hash_mismatch_before_replacing_targets(tmp_path: Path) -> None:
    identity, tenants = _source_state(tmp_path)
    archive = tmp_path / "snapshot.zip"
    create_backup(
        identity_database=identity,
        tenant_data_root=tenants,
        output=archive,
        confirm_quiesced=True,
    )

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive, "r") as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename.endswith("project.json"):
                content = b'{"name":"Tampered"}'
            target.writestr(info.filename, content)

    target_identity = tmp_path / "target" / "identity.sqlite3"
    target_tenants = tmp_path / "target-tenants"
    _identity(target_identity, "keep")

    with pytest.raises(BackupRestoreError, match="integrity verification"):
        restore_backup(
            archive=tampered,
            identity_database=target_identity,
            tenant_data_root=target_tenants,
            confirm_quiesced=True,
            replace_existing=True,
        )

    assert _read_identity(target_identity) == "keep"


def test_restore_rejects_archive_paths_not_declared_by_manifest(tmp_path: Path) -> None:
    identity, tenants = _source_state(tmp_path)
    archive = tmp_path / "snapshot.zip"
    create_backup(
        identity_database=identity,
        tenant_data_root=tenants,
        output=archive,
        confirm_quiesced=True,
    )

    hostile = tmp_path / "hostile.zip"
    with zipfile.ZipFile(archive, "r") as source, zipfile.ZipFile(hostile, "w") as target:
        for info in source.infolist():
            target.writestr(info.filename, source.read(info.filename))
        target.writestr("../outside.txt", b"bad")

    with pytest.raises(BackupRestoreError, match="unsafe path"):
        restore_backup(
            archive=hostile,
            identity_database=tmp_path / "restore" / "identity.sqlite3",
            tenant_data_root=tmp_path / "restore-tenants",
            confirm_quiesced=True,
        )
    assert not (tmp_path / "outside.txt").exists()


def test_backup_rejects_symbolic_links(tmp_path: Path) -> None:
    identity, tenants = _source_state(tmp_path)
    external = tmp_path / "external.txt"
    external.write_text("do not follow", encoding="utf-8")
    link = tenants / "linked.txt"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available on this platform")

    with pytest.raises(BackupRestoreError, match="symbolic link"):
        create_backup(
            identity_database=identity,
            tenant_data_root=tenants,
            output=tmp_path / "snapshot.zip",
            confirm_quiesced=True,
        )


def test_manifest_is_machine_readable_and_contains_no_source_paths(tmp_path: Path) -> None:
    identity, tenants = _source_state(tmp_path)
    archive = tmp_path / "snapshot.zip"
    create_backup(
        identity_database=identity,
        tenant_data_root=tenants,
        output=archive,
        confirm_quiesced=True,
        now=NOW,
    )

    with zipfile.ZipFile(archive, "r") as snapshot:
        manifest = json.loads(snapshot.read("manifest.json"))

    encoded = json.dumps(manifest)
    assert manifest["format_version"] == 1
    assert manifest["consistency"] == "operator_quiesced"
    assert str(identity.resolve()) not in encoded
    assert str(tenants.resolve()) not in encoded
