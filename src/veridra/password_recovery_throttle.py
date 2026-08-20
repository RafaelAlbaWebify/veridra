from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class PasswordRecoveryThrottleDecision:
    allowed: bool
    retry_after_seconds: int = 0


class SQLitePasswordRecoveryThrottle:
    """Persistent per-address throttling for password-reset issuance.

    The public recovery response must remain identical whether an account exists,
    is missing, or the address is currently throttled. Deployment-edge/IP rate
    limiting remains a separate reverse-proxy responsibility.
    """

    def __init__(
        self,
        database: Path,
        *,
        max_requests: int = 3,
        request_window: timedelta = timedelta(minutes=15),
        lockout_duration: timedelta = timedelta(minutes=15),
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be positive.")
        if request_window <= timedelta(0) or lockout_duration <= timedelta(0):
            raise ValueError("Throttle durations must be positive.")
        self.database = database
        self.max_requests = max_requests
        self.request_window = request_window
        self.lockout_duration = lockout_duration

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS password_recovery_throttle (
                    subject_hash TEXT PRIMARY KEY,
                    request_count INTEGER NOT NULL,
                    window_started_at TEXT NOT NULL,
                    locked_until TEXT
                )"""
            )

    @staticmethod
    def subject_hash(email: str) -> str:
        return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()

    def consume(
        self,
        *,
        email: str,
        now: datetime | None = None,
    ) -> PasswordRecoveryThrottleDecision:
        requested_at = (now or datetime.now(UTC)).astimezone(UTC)
        subject_hash = self.subject_hash(email)
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT request_count, window_started_at, locked_until
                FROM password_recovery_throttle WHERE subject_hash = ?""",
                (subject_hash,),
            ).fetchone()

            window_started_at = requested_at
            request_count = 1
            if row is not None:
                locked_until_raw = row["locked_until"]
                if locked_until_raw is not None:
                    locked_until = datetime.fromisoformat(locked_until_raw)
                    remaining = int((locked_until - requested_at).total_seconds())
                    if remaining > 0:
                        return PasswordRecoveryThrottleDecision(False, max(1, remaining))
                previous_window = datetime.fromisoformat(row["window_started_at"])
                if requested_at - previous_window <= self.request_window:
                    window_started_at = previous_window
                    request_count = int(row["request_count"]) + 1

            locked_until = None
            allowed = request_count <= self.max_requests
            if not allowed:
                locked_until = requested_at + self.lockout_duration

            connection.execute(
                """INSERT INTO password_recovery_throttle
                (subject_hash, request_count, window_started_at, locked_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(subject_hash) DO UPDATE SET
                    request_count=excluded.request_count,
                    window_started_at=excluded.window_started_at,
                    locked_until=excluded.locked_until""",
                (
                    subject_hash,
                    request_count,
                    window_started_at.isoformat(),
                    locked_until.isoformat() if locked_until is not None else None,
                ),
            )

        if allowed:
            return PasswordRecoveryThrottleDecision(True)
        return PasswordRecoveryThrottleDecision(
            False,
            max(1, int(self.lockout_duration.total_seconds())),
        )
