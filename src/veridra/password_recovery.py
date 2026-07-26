from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .identity_tenancy import AccountStatus, SessionStatus
from .password_auth import hash_password


class PasswordRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class IssuedPasswordReset:
    token: str
    email: str
    expires_at: datetime


class SQLitePasswordRecoveryService:
    def __init__(self, database: Path) -> None:
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS password_reset_tokens_user_idx
                ON password_reset_tokens(user_id)"""
            )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue(
        self,
        *,
        email: str,
        now: datetime | None = None,
        lifetime: timedelta = timedelta(minutes=30),
    ) -> IssuedPasswordReset | None:
        if lifetime <= timedelta(0):
            raise ValueError("Password-reset lifetime must be positive.")
        issued_at = (now or datetime.now(UTC)).astimezone(UTC)
        normalized_email = email.strip().lower()
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, status FROM users WHERE email = ?",
                (normalized_email,),
            ).fetchone()
            if row is None or AccountStatus(row["status"]) is not AccountStatus.active:
                return None
            token = secrets.token_urlsafe(48)
            expires_at = issued_at + lifetime
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE password_reset_tokens
                SET consumed_at = ?
                WHERE user_id = ? AND consumed_at IS NULL""",
                (issued_at.isoformat(), row["id"]),
            )
            connection.execute(
                """INSERT INTO password_reset_tokens
                (token_hash, user_id, issued_at, expires_at, consumed_at)
                VALUES (?, ?, ?, ?, NULL)""",
                (
                    self._token_hash(token),
                    row["id"],
                    issued_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return IssuedPasswordReset(
            token=token,
            email=normalized_email,
            expires_at=expires_at,
        )

    def reset_password(
        self,
        *,
        token: str,
        new_password: str,
        now: datetime | None = None,
    ) -> None:
        changed_at = (now or datetime.now(UTC)).astimezone(UTC)
        new_hash = hash_password(new_password)
        token_hash = self._token_hash(token)
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT user_id, expires_at, consumed_at
                FROM password_reset_tokens WHERE token_hash = ?""",
                (token_hash,),
            ).fetchone()
            if row is None or row["consumed_at"] is not None:
                raise PasswordRecoveryError("Password-reset token is invalid.")
            if datetime.fromisoformat(row["expires_at"]) <= changed_at:
                raise PasswordRecoveryError("Password-reset token is invalid.")
            connection.execute(
                """UPDATE password_credentials
                SET password_hash = ?, updated_at = ?
                WHERE user_id = ?""",
                (new_hash, changed_at.isoformat(), row["user_id"]),
            )
            connection.execute(
                """UPDATE sessions
                SET status = ?, revoked_at = ?
                WHERE user_id = ? AND status = ?""",
                (
                    SessionStatus.revoked.value,
                    changed_at.isoformat(),
                    row["user_id"],
                    SessionStatus.active.value,
                ),
            )
            connection.execute(
                """UPDATE password_reset_tokens
                SET consumed_at = ? WHERE user_id = ? AND consumed_at IS NULL""",
                (changed_at.isoformat(), row["user_id"]),
            )
