from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path


class CrawlJobError(RuntimeError):
    pass


class CrawlJobState(StrEnum):
    queued = "queued"
    leased = "leased"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


@dataclass(frozen=True)
class CrawlJob:
    id: str
    tenant_id: str
    project_id: str
    target_url: str
    crawl_profile: str
    page_budget: int
    pages_completed: int
    idempotency_key: str
    state: CrawlJobState
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    last_error: str | None
    assessment_id: str | None
    audit_reservation_id: str | None
    page_reservation_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CrawlJobLease:
    job: CrawlJob
    worker_token: str


def _validate_identifier(value: str, *, field: str) -> str:
    if len(value) != 24 or any(character not in "0123456789abcdef" for character in value):
        raise CrawlJobError(f"{field} must be 24 lowercase hexadecimal characters.")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise CrawlJobError("Job timestamps must be timezone-aware.")
    return value.astimezone(UTC)


def _decode_optional(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteCrawlJobStore:
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
                """CREATE TABLE IF NOT EXISTS crawl_jobs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    crawl_profile TEXT NOT NULL,
                    page_budget INTEGER NOT NULL,
                    pages_completed INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    next_attempt_at TEXT NOT NULL,
                    lease_token_hash TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    assessment_id TEXT,
                    audit_reservation_id TEXT,
                    page_reservation_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (state IN ('queued', 'leased', 'succeeded', 'failed', 'cancelled')),
                    CHECK (page_budget >= 1),
                    CHECK (pages_completed >= 0),
                    CHECK (pages_completed <= page_budget),
                    CHECK (attempt_count >= 0),
                    CHECK (max_attempts >= 1),
                    UNIQUE (tenant_id, id)
                )"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS crawl_jobs_due_idx
                ON crawl_jobs(state, next_attempt_at, created_at)"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS crawl_jobs_tenant_idx
                ON crawl_jobs(tenant_id, created_at DESC)"""
            )

    def enqueue(
        self,
        *,
        tenant_id: str,
        project_id: str,
        target_url: str,
        crawl_profile: str,
        page_budget: int,
        request_key: str,
        now: datetime,
        max_attempts: int = 3,
        max_active_for_tenant: int = 1,
        audit_reservation_id: str | None = None,
        page_reservation_id: str | None = None,
    ) -> CrawlJob:
        tenant_id = _validate_identifier(tenant_id, field="tenant_id")
        project_id = _validate_identifier(project_id, field="project_id")
        if not target_url.strip():
            raise CrawlJobError("target_url is required.")
        if not crawl_profile.strip():
            raise CrawlJobError("crawl_profile is required.")
        if not request_key.strip():
            raise CrawlJobError("request_key is required.")
        if page_budget < 1:
            raise CrawlJobError("page_budget must be at least 1.")
        if max_attempts < 1:
            raise CrawlJobError("max_attempts must be at least 1.")
        if max_active_for_tenant < 1:
            raise CrawlJobError("max_active_for_tenant must be at least 1.")
        timestamp = _utc(now)
        idempotency_key = hashlib.sha256(
            (
                f"{tenant_id}:{project_id}:{target_url}:{crawl_profile}:"
                f"{page_budget}:{request_key}"
            ).encode()
        ).hexdigest()
        job_id = idempotency_key[:24]
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM crawl_jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                return self._decode(existing)
            active_count = connection.execute(
                """SELECT COUNT(*) FROM crawl_jobs
                WHERE tenant_id = ? AND state IN (?, ?)""",
                (
                    tenant_id,
                    CrawlJobState.queued.value,
                    CrawlJobState.leased.value,
                ),
            ).fetchone()[0]
            if int(active_count) >= max_active_for_tenant:
                raise CrawlJobError("The tenant crawl-job concurrency allowance is exhausted.")
            connection.execute(
                """INSERT INTO crawl_jobs
                (id, tenant_id, project_id, target_url, crawl_profile, page_budget,
                 pages_completed, idempotency_key, state, attempt_count, max_attempts,
                 next_attempt_at, lease_token_hash, lease_expires_at, last_error,
                 assessment_id, audit_reservation_id, page_reservation_id,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 0, ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?)""",
                (
                    job_id,
                    tenant_id,
                    project_id,
                    target_url,
                    crawl_profile,
                    page_budget,
                    idempotency_key,
                    CrawlJobState.queued.value,
                    max_attempts,
                    timestamp.isoformat(),
                    audit_reservation_id,
                    page_reservation_id,
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is None:
            raise CrawlJobError("Crawl job could not be loaded after enqueue.")
        return self._decode(row)

    def list_for_tenant(self, tenant_id: str) -> tuple[CrawlJob, ...]:
        tenant_id = _validate_identifier(tenant_id, field="tenant_id")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM crawl_jobs WHERE tenant_id = ?
                ORDER BY created_at DESC, id DESC""",
                (tenant_id,),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def load(self, *, tenant_id: str, job_id: str) -> CrawlJob:
        tenant_id = _validate_identifier(tenant_id, field="tenant_id")
        job_id = _validate_identifier(job_id, field="job_id")
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM crawl_jobs WHERE tenant_id = ? AND id = ?",
                (tenant_id, job_id),
            ).fetchone()
        if row is None:
            raise CrawlJobError("Crawl job not found.")
        return self._decode(row)

    def lease_next(
        self,
        *,
        now: datetime,
        lease_duration: timedelta,
    ) -> CrawlJobLease | None:
        timestamp = _utc(now)
        if lease_duration <= timedelta(0):
            raise CrawlJobError("lease_duration must be positive.")
        lease_expires_at = timestamp + lease_duration
        worker_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(worker_token.encode()).hexdigest()
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM crawl_jobs
                WHERE (
                    state = ? AND next_attempt_at <= ?
                ) OR (
                    state = ? AND lease_expires_at <= ?
                )
                ORDER BY next_attempt_at, created_at, id
                LIMIT 1""",
                (
                    CrawlJobState.queued.value,
                    timestamp.isoformat(),
                    CrawlJobState.leased.value,
                    timestamp.isoformat(),
                ),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            updated = connection.execute(
                """UPDATE crawl_jobs
                SET state = ?, lease_token_hash = ?, lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND (
                    (state = ? AND next_attempt_at <= ?) OR
                    (state = ? AND lease_expires_at <= ?)
                )""",
                (
                    CrawlJobState.leased.value,
                    token_hash,
                    lease_expires_at.isoformat(),
                    timestamp.isoformat(),
                    row["id"],
                    CrawlJobState.queued.value,
                    timestamp.isoformat(),
                    CrawlJobState.leased.value,
                    timestamp.isoformat(),
                ),
            )
            if updated.rowcount != 1:
                connection.rollback()
                return None
            leased = connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (row["id"],),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if leased is None:
            raise CrawlJobError("Leased crawl job could not be reloaded.")
        return CrawlJobLease(job=self._decode(leased), worker_token=worker_token)

    def update_progress(
        self,
        *,
        job_id: str,
        worker_token: str,
        pages_completed: int,
        now: datetime,
    ) -> CrawlJob:
        job_id = _validate_identifier(job_id, field="job_id")
        timestamp = _utc(now)
        token_hash = hashlib.sha256(worker_token.encode()).hexdigest()
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT page_budget FROM crawl_jobs
                WHERE id = ? AND state = ? AND lease_token_hash = ?""",
                (job_id, CrawlJobState.leased.value, token_hash),
            ).fetchone()
            if row is None:
                raise CrawlJobError("Current crawl-job lease was not found.")
            if not 0 <= pages_completed <= int(row["page_budget"]):
                raise CrawlJobError("Crawl-job progress is outside the reserved page budget.")
            connection.execute(
                """UPDATE crawl_jobs SET pages_completed = ?, updated_at = ?
                WHERE id = ?""",
                (pages_completed, timestamp.isoformat(), job_id),
            )
        return self._load_by_id(job_id)

    def succeed(
        self,
        *,
        job_id: str,
        worker_token: str,
        now: datetime,
        pages_completed: int,
        assessment_id: str,
    ) -> CrawlJob:
        if not assessment_id.strip():
            raise CrawlJobError("assessment_id is required.")
        return self._finish(
            job_id=job_id,
            worker_token=worker_token,
            now=now,
            error=None,
            retry_delay=None,
            pages_completed=pages_completed,
            assessment_id=assessment_id,
        )

    def fail(
        self,
        *,
        job_id: str,
        worker_token: str,
        now: datetime,
        error: str,
        retry_delay: timedelta,
    ) -> CrawlJob:
        if not error.strip():
            raise CrawlJobError("error is required.")
        if retry_delay < timedelta(0):
            raise CrawlJobError("retry_delay cannot be negative.")
        return self._finish(
            job_id=job_id,
            worker_token=worker_token,
            now=now,
            error=error,
            retry_delay=retry_delay,
            pages_completed=None,
            assessment_id=None,
        )

    def cancel(self, *, tenant_id: str, job_id: str, now: datetime) -> CrawlJob:
        tenant_id = _validate_identifier(tenant_id, field="tenant_id")
        job_id = _validate_identifier(job_id, field="job_id")
        timestamp = _utc(now)
        self.initialize()
        with self._connect() as connection:
            updated = connection.execute(
                """UPDATE crawl_jobs
                SET state = ?, lease_token_hash = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE tenant_id = ? AND id = ? AND state IN (?, ?)""",
                (
                    CrawlJobState.cancelled.value,
                    timestamp.isoformat(),
                    tenant_id,
                    job_id,
                    CrawlJobState.queued.value,
                    CrawlJobState.leased.value,
                ),
            )
            if updated.rowcount != 1:
                raise CrawlJobError("Cancellable crawl job not found.")
        return self.load(tenant_id=tenant_id, job_id=job_id)

    def _finish(
        self,
        *,
        job_id: str,
        worker_token: str,
        now: datetime,
        error: str | None,
        retry_delay: timedelta | None,
        pages_completed: int | None,
        assessment_id: str | None,
    ) -> CrawlJob:
        job_id = _validate_identifier(job_id, field="job_id")
        timestamp = _utc(now)
        token_hash = hashlib.sha256(worker_token.encode()).hexdigest()
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM crawl_jobs
                WHERE id = ? AND state = ? AND lease_token_hash = ?""",
                (job_id, CrawlJobState.leased.value, token_hash),
            ).fetchone()
            if row is None:
                raise CrawlJobError("Current crawl-job lease was not found.")
            attempt_count = int(row["attempt_count"]) + 1
            completed = int(row["pages_completed"])
            if pages_completed is not None:
                if not 0 <= pages_completed <= int(row["page_budget"]):
                    raise CrawlJobError("Crawl-job progress is outside the reserved page budget.")
                completed = pages_completed
            if error is None:
                state = CrawlJobState.succeeded
                next_attempt_at = timestamp
                last_error = None
            elif attempt_count >= int(row["max_attempts"]):
                state = CrawlJobState.failed
                next_attempt_at = timestamp
                last_error = error
            else:
                state = CrawlJobState.queued
                next_attempt_at = timestamp + (retry_delay or timedelta(0))
                last_error = error
            connection.execute(
                """UPDATE crawl_jobs
                SET state = ?, attempt_count = ?, next_attempt_at = ?,
                    lease_token_hash = NULL, lease_expires_at = NULL,
                    last_error = ?, assessment_id = ?, pages_completed = ?, updated_at = ?
                WHERE id = ?""",
                (
                    state.value,
                    attempt_count,
                    next_attempt_at.isoformat(),
                    last_error,
                    assessment_id,
                    completed,
                    timestamp.isoformat(),
                    job_id,
                ),
            )
            finished = connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if finished is None:
            raise CrawlJobError("Crawl job could not be reloaded.")
        return self._decode(finished)

    def _load_by_id(self, job_id: str) -> CrawlJob:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise CrawlJobError("Crawl job not found.")
        return self._decode(row)

    @staticmethod
    def _decode(row: sqlite3.Row) -> CrawlJob:
        return CrawlJob(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            target_url=str(row["target_url"]),
            crawl_profile=str(row["crawl_profile"]),
            page_budget=int(row["page_budget"]),
            pages_completed=int(row["pages_completed"]),
            idempotency_key=str(row["idempotency_key"]),
            state=CrawlJobState(str(row["state"])),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            next_attempt_at=datetime.fromisoformat(str(row["next_attempt_at"])),
            lease_expires_at=_decode_optional(row["lease_expires_at"]),
            last_error=str(row["last_error"]) if row["last_error"] else None,
            assessment_id=str(row["assessment_id"]) if row["assessment_id"] else None,
            audit_reservation_id=(
                str(row["audit_reservation_id"]) if row["audit_reservation_id"] else None
            ),
            page_reservation_id=(
                str(row["page_reservation_id"]) if row["page_reservation_id"] else None
            ),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )
