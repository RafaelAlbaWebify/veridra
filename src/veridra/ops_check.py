from __future__ import annotations

import json
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .backup_restore import SnapshotManifest
from .identity_email_delivery import IdentityEmailAttempt


class OpsCheckError(RuntimeError):
    pass


class CheckStatus(StrEnum):
    ok = "ok"
    warning = "warning"
    critical = "critical"


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    status: CheckStatus
    count: int = Field(default=0, ge=0)
    detail: str = Field(min_length=1, max_length=200)


class OpsCheckReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CheckStatus
    checked_at: datetime
    checks: list[CheckResult]

    @property
    def exit_code(self) -> int:
        if self.status is CheckStatus.critical:
            return 2
        if self.status is CheckStatus.warning:
            return 1
        return 0


@dataclass(frozen=True)
class OpsCheckConfig:
    identity_database: Path
    tenant_data_root: Path
    recent_window: timedelta = timedelta(hours=24)
    queued_overdue: timedelta = timedelta(minutes=30)
    backup_directory: Path | None = None
    backup_max_age: timedelta = timedelta(hours=26)


def _overall(checks: list[CheckResult]) -> CheckStatus:
    statuses = {check.status for check in checks}
    if CheckStatus.critical in statuses:
        return CheckStatus.critical
    if CheckStatus.warning in statuses:
        return CheckStatus.warning
    return CheckStatus.ok


def _identity_check(database: Path) -> CheckResult:
    if not database.is_file() or database.is_symlink():
        return CheckResult(
            name="identity_database",
            status=CheckStatus.critical,
            detail="identity database is unavailable",
        )
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
    except sqlite3.Error:
        integrity = None
        rows = []
    required = {"tenants", "users", "memberships", "sessions"}
    tables = {str(row[0]) for row in rows}
    if integrity is None or integrity[0] != "ok" or not required.issubset(tables):
        return CheckResult(
            name="identity_database",
            status=CheckStatus.critical,
            detail="identity database integrity or schema check failed",
        )
    return CheckResult(
        name="identity_database",
        status=CheckStatus.ok,
        detail="identity database is readable",
    )


def _tenant_root_check(root: Path) -> CheckResult:
    if not root.is_dir() or root.is_symlink():
        return CheckResult(
            name="tenant_data_root",
            status=CheckStatus.critical,
            detail="tenant data root is unavailable",
        )
    try:
        next(root.iterdir(), None)
    except OSError:
        return CheckResult(
            name="tenant_data_root",
            status=CheckStatus.critical,
            detail="tenant data root cannot be read",
        )
    return CheckResult(
        name="tenant_data_root",
        status=CheckStatus.ok,
        detail="tenant data root is readable",
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _monitoring_checks(
    root: Path,
    *,
    now: datetime,
    recent_window: timedelta,
    queued_overdue: timedelta,
) -> list[CheckResult]:
    database = root / "monitoring-jobs.sqlite3"
    if not database.exists():
        return [
            CheckResult(
                name="monitoring_jobs",
                status=CheckStatus.ok,
                detail="monitoring job store is not initialized",
            )
        ]
    if not database.is_file() or database.is_symlink():
        return [
            CheckResult(
                name="monitoring_jobs",
                status=CheckStatus.critical,
                detail="monitoring job store is unavailable",
            )
        ]
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            rows = connection.execute(
                """SELECT state, next_attempt_at, lease_expires_at, updated_at
                FROM monitoring_jobs"""
            ).fetchall()
    except sqlite3.Error:
        return [
            CheckResult(
                name="monitoring_jobs",
                status=CheckStatus.critical,
                detail="monitoring job store cannot be queried",
            )
        ]
    if integrity is None or integrity[0] != "ok":
        return [
            CheckResult(
                name="monitoring_jobs",
                status=CheckStatus.critical,
                detail="monitoring job store integrity check failed",
            )
        ]

    recent_cutoff = now - recent_window
    overdue_cutoff = now - queued_overdue
    failed = 0
    overdue = 0
    expired_leases = 0
    malformed = 0
    for row in rows:
        updated_at = _parse_timestamp(row["updated_at"])
        next_attempt_at = _parse_timestamp(row["next_attempt_at"])
        lease_expires_at = _parse_timestamp(row["lease_expires_at"])
        state = str(row["state"])
        if updated_at is None or next_attempt_at is None:
            malformed += 1
            continue
        if state == "failed" and updated_at >= recent_cutoff:
            failed += 1
        elif state == "queued" and next_attempt_at <= overdue_cutoff:
            overdue += 1
        elif state == "leased":
            if lease_expires_at is None:
                malformed += 1
            elif lease_expires_at <= now:
                expired_leases += 1

    checks = [
        CheckResult(
            name="monitoring_failed_recent",
            status=CheckStatus.critical if failed else CheckStatus.ok,
            count=failed,
            detail="recent terminal monitoring jobs" if failed else "no recent terminal jobs",
        ),
        CheckResult(
            name="monitoring_queue_overdue",
            status=CheckStatus.warning if overdue else CheckStatus.ok,
            count=overdue,
            detail="monitoring jobs are overdue" if overdue else "monitoring queue is within threshold",
        ),
        CheckResult(
            name="monitoring_expired_leases",
            status=CheckStatus.critical if expired_leases else CheckStatus.ok,
            count=expired_leases,
            detail="monitoring leases expired" if expired_leases else "no expired monitoring leases",
        ),
    ]
    if malformed:
        checks.append(
            CheckResult(
                name="monitoring_malformed_rows",
                status=CheckStatus.critical,
                count=malformed,
                detail="monitoring job timestamps are invalid",
            )
        )
    return checks


def _identity_email_checks(
    database: Path,
    *,
    now: datetime,
    recent_window: timedelta,
) -> list[CheckResult]:
    directory = database.parent / "identity-email-deliveries"
    if not directory.exists():
        return [
            CheckResult(
                name="identity_email_failures",
                status=CheckStatus.ok,
                detail="identity email evidence is not initialized",
            )
        ]
    if not directory.is_dir() or directory.is_symlink():
        return [
            CheckResult(
                name="identity_email_evidence",
                status=CheckStatus.critical,
                detail="identity email evidence is unavailable",
            )
        ]
    cutoff = now - recent_window
    failures = 0
    malformed = 0
    for path in directory.glob("*.json"):
        if not path.is_file() or path.is_symlink():
            malformed += 1
            continue
        try:
            attempt = IdentityEmailAttempt.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            malformed += 1
            continue
        if attempt.status.value == "failed" and attempt.attempted_at.astimezone(UTC) >= cutoff:
            failures += 1
    checks = [
        CheckResult(
            name="identity_email_failures",
            status=CheckStatus.warning if failures else CheckStatus.ok,
            count=failures,
            detail=(
                "recent identity email failures" if failures else "no recent identity email failures"
            ),
        )
    ]
    if malformed:
        checks.append(
            CheckResult(
                name="identity_email_evidence",
                status=CheckStatus.warning,
                count=malformed,
                detail="identity email evidence contains unreadable records",
            )
        )
    return checks


def _backup_created_at(path: Path) -> datetime | None:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            if "manifest.json" not in archive.namelist():
                return None
            manifest = SnapshotManifest.model_validate_json(archive.read("manifest.json"))
    except (OSError, ValueError, ValidationError, zipfile.BadZipFile):
        return None
    if manifest.format_version != 1 or manifest.consistency != "operator_quiesced":
        return None
    if manifest.created_at.tzinfo is None:
        return None
    return manifest.created_at.astimezone(UTC)


def _backup_check(
    directory: Path,
    *,
    now: datetime,
    max_age: timedelta,
) -> CheckResult:
    if not directory.is_dir() or directory.is_symlink():
        return CheckResult(
            name="backup_freshness",
            status=CheckStatus.critical,
            detail="backup directory is unavailable",
        )
    created = [
        timestamp
        for path in directory.glob("*.zip")
        if path.is_file()
        and not path.is_symlink()
        and (timestamp := _backup_created_at(path)) is not None
    ]
    if not created:
        return CheckResult(
            name="backup_freshness",
            status=CheckStatus.critical,
            detail="no valid Veridra backup archive was found",
        )
    newest = max(created)
    stale = now - newest > max_age
    return CheckResult(
        name="backup_freshness",
        status=CheckStatus.critical if stale else CheckStatus.ok,
        detail="latest backup is stale" if stale else "latest backup is within threshold",
    )


def run_ops_check(
    config: OpsCheckConfig,
    *,
    now: datetime | None = None,
) -> OpsCheckReport:
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if config.recent_window <= timedelta(0):
        raise OpsCheckError("recent_window must be positive")
    if config.queued_overdue <= timedelta(0):
        raise OpsCheckError("queued_overdue must be positive")
    if config.backup_max_age <= timedelta(0):
        raise OpsCheckError("backup_max_age must be positive")

    identity = config.identity_database.expanduser().resolve()
    tenant_root = config.tenant_data_root.expanduser().resolve()
    checks = [_identity_check(identity), _tenant_root_check(tenant_root)]
    if checks[1].status is not CheckStatus.critical:
        checks.extend(
            _monitoring_checks(
                tenant_root,
                now=checked_at,
                recent_window=config.recent_window,
                queued_overdue=config.queued_overdue,
            )
        )
    checks.extend(
        _identity_email_checks(
            identity,
            now=checked_at,
            recent_window=config.recent_window,
        )
    )
    if config.backup_directory is not None:
        checks.append(
            _backup_check(
                config.backup_directory.expanduser().resolve(),
                now=checked_at,
                max_age=config.backup_max_age,
            )
        )
    return OpsCheckReport(status=_overall(checks), checked_at=checked_at, checks=checks)


def report_json(report: OpsCheckReport) -> str:
    return json.dumps(report.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
