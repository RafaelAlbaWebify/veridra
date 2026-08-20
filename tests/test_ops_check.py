from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from veridra.backup_restore import create_backup
from veridra.email_delivery import EmailStatus
from veridra.identity_email_delivery import IdentityEmailAttempt, IdentityEmailKind
from veridra.ops_check import (
    CheckStatus,
    OpsCheckConfig,
    OpsCheckReport,
    report_json,
    run_ops_check,
)

NOW = datetime(2026, 8, 20, 16, 30, tzinfo=UTC)


def _identity(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE memberships (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO users VALUES ('user-1')")


def _monitoring_database(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    database = root / "monitoring-jobs.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE monitoring_jobs (
                state TEXT NOT NULL,
                next_attempt_at TEXT NOT NULL,
                lease_expires_at TEXT,
                updated_at TEXT NOT NULL
            )"""
        )
    return database


def _insert_job(
    database: Path,
    *,
    state: str,
    next_attempt_at: datetime,
    updated_at: datetime,
    lease_expires_at: datetime | None = None,
) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO monitoring_jobs VALUES (?, ?, ?, ?)",
            (
                state,
                next_attempt_at.isoformat(),
                lease_expires_at.isoformat() if lease_expires_at else None,
                updated_at.isoformat(),
            ),
        )


def _base(tmp_path: Path) -> tuple[Path, Path]:
    identity = tmp_path / "identity" / "identity.sqlite3"
    tenants = tmp_path / "tenants"
    _identity(identity)
    tenants.mkdir()
    return identity, tenants


def _check(report: OpsCheckReport, name: str) -> dict[str, object]:
    payload = json.loads(report_json(report))
    return next(check for check in payload["checks"] if check["name"] == name)


def _backup(
    *,
    identity: Path,
    tenants: Path,
    directory: Path,
    created_at: datetime,
    name: str = "snapshot.zip",
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / name
    create_backup(
        identity_database=identity,
        tenant_data_root=tenants,
        output=archive,
        confirm_quiesced=True,
        now=created_at,
    )
    return archive


def test_healthy_uninitialized_runtime_is_ok(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)

    report = run_ops_check(
        OpsCheckConfig(identity_database=identity, tenant_data_root=tenants),
        now=NOW,
    )

    assert report.status is CheckStatus.ok
    assert report.exit_code == 0
    assert _check(report, "identity_database")["status"] == "ok"
    assert _check(report, "monitoring_jobs")["status"] == "ok"


def test_identity_schema_gap_is_critical(tmp_path: Path) -> None:
    identity = tmp_path / "identity" / "identity.sqlite3"
    identity.parent.mkdir(parents=True)
    with sqlite3.connect(identity) as connection:
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
    tenants = tmp_path / "tenants"
    tenants.mkdir()

    report = run_ops_check(
        OpsCheckConfig(identity_database=identity, tenant_data_root=tenants),
        now=NOW,
    )

    assert report.status is CheckStatus.critical
    assert _check(report, "identity_database")["status"] == "critical"


def test_recent_terminal_monitoring_job_is_critical(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)
    database = _monitoring_database(tenants)
    _insert_job(
        database,
        state="failed",
        next_attempt_at=NOW,
        updated_at=NOW - timedelta(minutes=5),
    )

    report = run_ops_check(
        OpsCheckConfig(identity_database=identity, tenant_data_root=tenants),
        now=NOW,
    )

    assert report.status is CheckStatus.critical
    assert report.exit_code == 2
    assert _check(report, "monitoring_failed_recent")["count"] == 1


def test_overdue_monitoring_queue_is_warning(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)
    database = _monitoring_database(tenants)
    _insert_job(
        database,
        state="queued",
        next_attempt_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(hours=2),
    )

    report = run_ops_check(
        OpsCheckConfig(identity_database=identity, tenant_data_root=tenants),
        now=NOW,
    )

    assert report.status is CheckStatus.warning
    assert report.exit_code == 1
    assert _check(report, "monitoring_queue_overdue")["count"] == 1


def test_expired_monitoring_lease_is_critical(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)
    database = _monitoring_database(tenants)
    _insert_job(
        database,
        state="leased",
        next_attempt_at=NOW - timedelta(minutes=20),
        updated_at=NOW - timedelta(minutes=20),
        lease_expires_at=NOW - timedelta(minutes=1),
    )

    report = run_ops_check(
        OpsCheckConfig(identity_database=identity, tenant_data_root=tenants),
        now=NOW,
    )

    assert report.status is CheckStatus.critical
    assert _check(report, "monitoring_expired_leases")["count"] == 1


def test_recent_identity_email_failure_warns_without_exposing_recipient(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)
    attempt = IdentityEmailAttempt(
        kind=IdentityEmailKind.password_reset,
        recipient="customer@example.com",
        attempted_at=NOW - timedelta(minutes=10),
        status=EmailStatus.failed,
        subject="Password reset",
        message_sha256="a" * 64,
        delivery_key="b" * 24,
        error="provider secret detail",
    )
    directory = identity.parent / "identity-email-deliveries"
    directory.mkdir()
    (directory / "attempt.json").write_text(
        attempt.model_dump_json(),
        encoding="utf-8",
    )

    report = run_ops_check(
        OpsCheckConfig(identity_database=identity, tenant_data_root=tenants),
        now=NOW,
    )
    encoded = report_json(report)

    assert report.status is CheckStatus.warning
    assert _check(report, "identity_email_failures")["count"] == 1
    assert "customer@example.com" not in encoded
    assert "provider secret detail" not in encoded
    assert str(identity) not in encoded


def test_malformed_identity_email_evidence_warns_independently(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)
    directory = identity.parent / "identity-email-deliveries"
    directory.mkdir()
    (directory / "broken.json").write_text("not-json", encoding="utf-8")

    report = run_ops_check(
        OpsCheckConfig(identity_database=identity, tenant_data_root=tenants),
        now=NOW,
    )

    assert report.status is CheckStatus.warning
    assert _check(report, "identity_email_failures")["count"] == 0
    assert _check(report, "identity_email_evidence")["count"] == 1


def test_missing_explicit_backup_directory_is_critical(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)

    report = run_ops_check(
        OpsCheckConfig(
            identity_database=identity,
            tenant_data_root=tenants,
            backup_directory=tmp_path / "missing-backups",
        ),
        now=NOW,
    )

    assert report.status is CheckStatus.critical
    assert _check(report, "backup_freshness")["status"] == "critical"


def test_recent_valid_backup_manifest_is_ok(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)
    backups = tmp_path / "backups"
    _backup(
        identity=identity,
        tenants=tenants,
        directory=backups,
        created_at=NOW - timedelta(hours=2),
    )

    report = run_ops_check(
        OpsCheckConfig(
            identity_database=identity,
            tenant_data_root=tenants,
            backup_directory=backups,
            backup_max_age=timedelta(hours=4),
        ),
        now=NOW,
    )

    assert _check(report, "backup_freshness")["status"] == "ok"


def test_stale_valid_backup_manifest_is_critical(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)
    backups = tmp_path / "backups"
    _backup(
        identity=identity,
        tenants=tenants,
        directory=backups,
        created_at=NOW - timedelta(days=2),
    )

    report = run_ops_check(
        OpsCheckConfig(
            identity_database=identity,
            tenant_data_root=tenants,
            backup_directory=backups,
            backup_max_age=timedelta(hours=26),
        ),
        now=NOW,
    )

    assert report.status is CheckStatus.critical
    assert _check(report, "backup_freshness")["status"] == "critical"


def test_random_zip_does_not_satisfy_backup_freshness(tmp_path: Path) -> None:
    identity, tenants = _base(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "random.zip").write_bytes(b"not a Veridra snapshot")

    report = run_ops_check(
        OpsCheckConfig(
            identity_database=identity,
            tenant_data_root=tenants,
            backup_directory=backups,
        ),
        now=NOW,
    )

    assert report.status is CheckStatus.critical
    assert _check(report, "backup_freshness")["status"] == "critical"


def test_corrupt_identity_database_is_critical_and_output_is_generic(tmp_path: Path) -> None:
    identity = tmp_path / "secret-location" / "identity.sqlite3"
    identity.parent.mkdir()
    identity.write_bytes(b"not sqlite")
    tenants = tmp_path / "tenants"
    tenants.mkdir()

    report = run_ops_check(
        OpsCheckConfig(identity_database=identity, tenant_data_root=tenants),
        now=NOW,
    )
    encoded = report_json(report)

    assert report.status is CheckStatus.critical
    assert _check(report, "identity_database")["status"] == "critical"
    assert "secret-location" not in encoded
