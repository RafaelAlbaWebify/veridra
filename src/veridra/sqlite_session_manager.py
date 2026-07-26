from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .identity_tenancy import AuthSession, SessionStatus


class SessionManagementError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionSummary:
    id: str
    tenant_id: str
    status: SessionStatus
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    current: bool


def _credential_hash(credential: str) -> str:
    if len(credential) < 32:
        raise SessionManagementError("Session credential is too short.")
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


class SQLiteSessionManager:
    def __init__(self, database: Path) -> None:
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def rotate(
        self,
        *,
        current_session_id: str,
        tenant_id: str,
        replacement_credential: str,
        replacement_session: AuthSession,
        revoked_at: datetime,
    ) -> None:
        credential_hash = _credential_hash(replacement_credential)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """SELECT user_id, tenant_id, status
                FROM sessions WHERE id = ?""",
                (current_session_id,),
            ).fetchone()
            if current is None:
                raise SessionManagementError("Current session was not found.")
            if current["status"] != SessionStatus.active.value:
                raise SessionManagementError("Current session is not active.")
            if (
                current["user_id"] != replacement_session.user_id
                or current["tenant_id"] != tenant_id
            ):
                raise SessionManagementError(
                    "Replacement session scope does not match the current session."
                )
            connection.execute(
                """INSERT INTO sessions
                (id, credential_hash, user_id, tenant_id, status, issued_at,
                 expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    replacement_session.id,
                    credential_hash,
                    replacement_session.user_id,
                    tenant_id,
                    replacement_session.status.value,
                    replacement_session.issued_at.isoformat(),
                    replacement_session.expires_at.isoformat(),
                    replacement_session.revoked_at.isoformat()
                    if replacement_session.revoked_at
                    else None,
                ),
            )
            updated = connection.execute(
                """UPDATE sessions SET status = ?, revoked_at = ?
                WHERE id = ? AND status = ?""",
                (
                    SessionStatus.revoked.value,
                    revoked_at.isoformat(),
                    current_session_id,
                    SessionStatus.active.value,
                ),
            )
            if updated.rowcount != 1:
                raise SessionManagementError(
                    "Current session could not be revoked."
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_for_user(
        self,
        *,
        user_id: str,
        current_session_id: str,
    ) -> tuple[SessionSummary, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, tenant_id, status, issued_at, expires_at, revoked_at
                FROM sessions WHERE user_id = ?
                ORDER BY issued_at DESC, id DESC""",
                (user_id,),
            ).fetchall()
        return tuple(
            SessionSummary(
                id=row["id"],
                tenant_id=row["tenant_id"],
                status=SessionStatus(row["status"]),
                issued_at=datetime.fromisoformat(row["issued_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                revoked_at=datetime.fromisoformat(row["revoked_at"])
                if row["revoked_at"]
                else None,
                current=row["id"] == current_session_id,
            )
            for row in rows
        )

    def revoke_for_user(
        self,
        *,
        user_id: str,
        session_id: str,
        current_session_id: str,
        revoked_at: datetime,
    ) -> None:
        if session_id == current_session_id:
            raise SessionManagementError(
                "The current session must be ended through logout."
            )
        with self._connect() as connection:
            updated = connection.execute(
                """UPDATE sessions SET status = ?, revoked_at = ?
                WHERE id = ? AND user_id = ? AND status = ?""",
                (
                    SessionStatus.revoked.value,
                    revoked_at.isoformat(),
                    session_id,
                    user_id,
                    SessionStatus.active.value,
                ),
            )
            if updated.rowcount != 1:
                raise SessionManagementError("Active session was not found.")
