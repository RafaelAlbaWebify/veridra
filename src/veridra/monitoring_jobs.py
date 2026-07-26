from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path


class MonitoringJobError(RuntimeError):
    pass


class MonitoringJobState(StrEnum):
    queued = "queued"
    leased = "leased"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


@dataclass(frozen=True)
class MonitoringJob:
    id: str
    tenant_id: str
    project_id: str
    run_window: str
    idempotency_key: str
    state: MonitoringJobState
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MonitoringJobLease:
    job: MonitoringJob
    worker_token: str


def _validate_identifier(value: str, *, field: str) -> str:
    if len(value) != 24 or any(character not in "0123456789abcdef" for character in value):
        raise MonitoringJobError(f"{field} must be 24 lowercase hexadecimal characters.")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise MonitoringJobError("Job timestamps must be timezone-aware.")
    return value.astimezone(UTC)


def _decode_optional(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteMonitoringJobStore:
    def __init__(self, database: Path) -> None:
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS monitoring_jobs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    run_window TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    next_attempt_at TEXT NOT NULL,
                    lease_token_hash TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (state IN ('queued', 'leased', 'succeeded', 'failed', 'cancelled')),
                    CHECK (attempt_count >= 0),
                    CHECK (max_attempts >= 1),
                    UNIQUE (tenant_id, id)
                )"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS monitoring_jobs_due_idx
                ON monitoring_jobs(state, next_attempt_at, created_at)"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS monitoring_jobs_tenant_idx
                ON monitoring_jobs(tenant_id, created_at DESC)"""
            )

    def enqueue(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_window: str,
        now: datetime,
        max_attempts: int = 3,
    ) -> MonitoringJob:
        tenant_id = _validate_identifier(tenant_id, field="tenant_id")
        project_id = _validate_identifier(project_id, field="project_id")
        if not run_window.strip():
            raise MonitoringJobError("run_window is required.")
        if max_attempts < 1:
            raise MonitoringJobError("max_attempts must be at least 1.")
        timestamp = _utc(now)
        idempotency_key = hashlib.sha256(
            f"{tenant_id}:{project_id}:{run_window}".encode("utf-8")
        ).hexdigest()
        job_id = idempotency_key[:24]
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO monitoring_jobs
                (id, tenant_id, project_id, run_window, idempotency_key, state,
                 attempt_count, max_attempts, next_attempt_at, lease_token_hash,
                 lease_expires_at, last_error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, NULL, NULL, ?, ?)""",
                (
                    job_id,
                    tenant_id,
                    project_id,
                    run_window,
                    idempotency_key,
                    MonitoringJobState.queued.value,
                    max_attempts,
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM monitoring_jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            raise MonitoringJobError("Monitoring job could not be loaded after enqueue.")
        return self._decode(row)

    def list_for_tenant(self, tenant_id: str) -> tuple[MonitoringJob, ...]:
        tenant_id = _validate_identifier(tenant_id, field="tenant_id")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM monitoring_jobs WHERE tenant_id = ?
                ORDER BY created_at DESC, id DESC""",
                (tenant_id,),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def load(self, *, tenant_id: str, job_id: str) -> MonitoringJob:
        tenant_id = _validate_identifier(tenant_id, field="tenant_id")
        job_id = _validate_identifier(job_id, field="job_id")
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM monitoring_jobs WHERE tenant_id = ? AND id = ?",
                (tenant_id, job_id),
            ).fetchone()
        if row is None:
            raise MonitoringJobError("Monitoring job not found.")
        return self._decode(row)

    def lease_next(
        self,
        *,
        now: datetime,
        lease_duration: timedelta,
    ) -> MonitoringJobLease | None:
        timestamp = _utc(now)
        if lease_duration <= timedelta(0):
            raise MonitoringJobError("lease_duration must be positive.")
        lease_expires_at = timestamp + lease_duration
        worker_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(worker_token.encode("utf-8")).hexdigest()
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM monitoring_jobs
                WHERE (
                    state = ? AND next_attempt_at <= ?
                ) OR (
                    state = ? AND lease_expires_at <= ?
                )
                ORDER BY next_attempt_at, created_at, id
                LIMIT 1""",
                (
                    MonitoringJobState.queued.value,
                    timestamp.isoformat(),
                    MonitoringJobState.leased.value,
                    timestamp.isoformat(),
                ),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            updated = connection.execute(
                """UPDATE monitoring_jobs
                SET state = ?, lease_token_hash = ?, lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND (
                    (state = ? AND next_attempt_at <= ?) OR
                    (state = ? AND lease_expires_at <= ?)
                )""",
                (
                    MonitoringJobState.leased.value,
                    token_hash,
                    lease_expires_at.isoformat(),
                    timestamp.isoformat(),
                    row["id"],
                    MonitoringJobState.queued.value,
                    timestamp.isoformat(),
                    MonitoringJobState.leased.value,
                    timestamp.isoformat(),
                ),
            )
            if updated.rowcount != 1:
                connection.rollback()
                return None
            leased = connection.execute(
                "SELECT * FROM monitoring_jobs WHERE id = ?",
                (row["id"],),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if leased is None:
            raise MonitoringJobError("Leased job could not be reloaded.")
        return MonitoringJobLease(job=self._decode(leased), worker_token=worker_token)

    def succeed(
        self,
        *,
        job_id: str,
        worker_token: str,
        now: datetime,
    ) -> MonitoringJob:
        return self._finish(
            job_id=job_id,
            worker_token=worker_token,
            now=now,
            error=None,
            retry_delay=None,
        )

    def fail(
        self,
        *,
        job_id: str,
        worker_token: str,
        now: datetime,
        error: str,
        retry_delay: timedelta,
    ) -> MonitoringJob:
        if not error.strip():
            raise MonitoringJobError("error is required.")
        if retry_delay < timedelta(0):
            raise MonitoringJobError("retry_delay cannot be negative.")
        return self._finish(
            job_id=job_id,
            worker_token=worker_token,
            now=now,
            error=error,
            retry_delay=retry_delay,
        )

    def cancel(self, *, tenant_id: str, job_id: str, now: datetime) -> MonitoringJob:
        tenant_id = _validate_identifier(tenant_id, field="tenant_id")
        job_id = _validate_identifier(job_id, field="job_id")
        timestamp = _utc(now)
        self.initialize()
        with self._connect() as connection:
            updated = connection.execute(
                """UPDATE monitoring_jobs
                SET state = ?, lease_token_hash = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE tenant_id = ? AND id = ? AND state IN (?, ?)""",
                (
                    MonitoringJobState.cancelled.value,
                    timestamp.isoformat(),
                    tenant_id,
                    job_id,
                    MonitoringJobState.queued.value,
                    MonitoringJobState.leased.value,
                ),
            )
            if updated.rowcount != 1:
                raise MonitoringJobError("Cancellable monitoring job not found.")
        return self.load(tenant_id=tenant_id, job_id=job_id)

    def _finish(
        self,
        *,
        job_id: str,
        worker_token: str,
        now: datetime,
        error: str | None,
        retry_delay: timedelta | None,
    ) -> MonitoringJob:
        job_id = _validate_identifier(job_id, field="job_id")
        timestamp = _utc(now)
        token_hash = hashlib.sha256(worker_token.encode("utf-8")).hexdigest()
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM monitoring_jobs
                WHERE id = ? AND state = ? AND lease_token_hash = ?""",
                (job_id, MonitoringJobState.leased.value, token_hash),
            ).fetchone()
            if row is None:
                raise MonitoringJobError("Current monitoring-job lease was not found.")
            attempt_count = int(row["attempt_count"]) + 1
            if error is None:
                state = MonitoringJobState.succeeded
                next_attempt_at = timestamp
                last_error = None
            elif attempt_count >= int(row["max_attempts"]):
                state = MonitoringJobState.failed
                next_attempt_at = timestamp
                last_error = error
            else:
                state = MonitoringJobState.queued
                next_attempt_at = timestamp + (retry_delay or timedelta(0))
                last_error = error
            connection.execute(
                """UPDATE monitoring_jobs
                SET state = ?, attempt_count = ?, next_attempt_at = ?,
                    lease_token_hash = NULL, lease_expires_at = NULL,
                    last_error = ?, updated_at = ?
                WHERE id = ?""",
                (
                    state.value,
                    attempt_count,
                    next_attempt_at.isoformat(),
                    last_error,
                    timestamp.isoformat(),
                    job_id,
                ),
            )
            finished = connection.execute(
                "SELECT * FROM monitoring_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if finished is None:
            raise MonitoringJobError("Monitoring job could not be reloaded.")
        return self._decode(finished)

    @staticmethod
    def _decode(row: sqlite3.Row) -> MonitoringJob:
        return MonitoringJob(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            run_window=str(row["run_window"]),
            idempotency_key=str(row["idempotency_key"]),
            state=MonitoringJobState(str(row["state"])),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            next_attempt_at=datetime.fromisoformat(str(row["next_attempt_at"])),
            lease_expires_at=_decode_optional(row["lease_expires_at"]),
            last_error=str(row["last_error"]) if row["last_error"] else None,
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )
