from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class LoginThrottleDecision:
    allowed: bool
    retry_after_seconds: int = 0


class SQLiteLoginThrottle:
    """Persistent credential-key throttling for password authentication.

    This protects one normalized email and tenant pair. Network-level or IP throttling
    remains a reverse-proxy or deployment-edge responsibility.
    """

    def __init__(
        self,
        database: Path,
        *,
        max_failures: int = 5,
        failure_window: timedelta = timedelta(minutes=15),
        lockout_duration: timedelta = timedelta(minutes=15),
    ) -> None:
        if max_failures < 1:
            raise ValueError("max_failures must be positive.")
        if failure_window <= timedelta(0) or lockout_duration <= timedelta(0):
            raise ValueError("Throttle durations must be positive.")
        self.database = database
        self.max_failures = max_failures
        self.failure_window = failure_window
        self.lockout_duration = lockout_duration

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS login_throttle (
                    subject_hash TEXT PRIMARY KEY,
                    failure_count INTEGER NOT NULL,
                    window_started_at TEXT NOT NULL,
                    locked_until TEXT
                )"""
            )

    @staticmethod
    def subject_hash(*, email: str, tenant_slug: str) -> str:
        normalized = f"{email.strip().lower()}\n{tenant_slug.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def check(self, *, email: str, tenant_slug: str, now: datetime | None = None) -> LoginThrottleDecision:
        checked_at = (now or datetime.now(UTC)).astimezone(UTC)
        subject_hash = self.subject_hash(email=email, tenant_slug=tenant_slug)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT locked_until FROM login_throttle WHERE subject_hash = ?",
                (subject_hash,),
            ).fetchone()
        if row is None or row["locked_until"] is None:
            return LoginThrottleDecision(allowed=True)
        locked_until = datetime.fromisoformat(row["locked_until"])
        remaining = int((locked_until - checked_at).total_seconds())
        if remaining <= 0:
            self.clear(email=email, tenant_slug=tenant_slug)
            return LoginThrottleDecision(allowed=True)
        return LoginThrottleDecision(allowed=False, retry_after_seconds=max(1, remaining))

    def record_failure(
        self,
        *,
        email: str,
        tenant_slug: str,
        now: datetime | None = None,
    ) -> LoginThrottleDecision:
        failed_at = (now or datetime.now(UTC)).astimezone(UTC)
        subject_hash = self.subject_hash(email=email, tenant_slug=tenant_slug)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT failure_count, window_started_at, locked_until
                FROM login_throttle WHERE subject_hash = ?""",
                (subject_hash,),
            ).fetchone()
            window_started_at = failed_at
            failure_count = 1
            if row is not None:
                existing_lock = row["locked_until"]
                if existing_lock is not None and datetime.fromisoformat(existing_lock) > failed_at:
                    remaining = int((datetime.fromisoformat(existing_lock) - failed_at).total_seconds())
                    return LoginThrottleDecision(False, max(1, remaining))
                previous_window = datetime.fromisoformat(row["window_started_at"])
                if failed_at - previous_window <= self.failure_window:
                    window_started_at = previous_window
                    failure_count = int(row["failure_count"]) + 1
            locked_until = None
            if failure_count >= self.max_failures:
                locked_until = failed_at + self.lockout_duration
            connection.execute(
                """INSERT INTO login_throttle
                (subject_hash, failure_count, window_started_at, locked_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(subject_hash) DO UPDATE SET
                    failure_count=excluded.failure_count,
                    window_started_at=excluded.window_started_at,
                    locked_until=excluded.locked_until""",
                (
                    subject_hash,
                    failure_count,
                    window_started_at.isoformat(),
                    locked_until.isoformat() if locked_until is not None else None,
                ),
            )
        if locked_until is None:
            return LoginThrottleDecision(allowed=True)
        return LoginThrottleDecision(
            allowed=False,
            retry_after_seconds=max(1, int(self.lockout_duration.total_seconds())),
        )

    def clear(self, *, email: str, tenant_slug: str) -> None:
        subject_hash = self.subject_hash(email=email, tenant_slug=tenant_slug)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM login_throttle WHERE subject_hash = ?",
                (subject_hash,),
            )
