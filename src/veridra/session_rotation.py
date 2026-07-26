from __future__ import annotations

from datetime import datetime

from .identity_tenancy import AuthSession, SessionStatus
from .sqlite_identity_store import SQLiteIdentityRecordStore, _credential_hash, _timestamp


def rotate_session_atomically(
    store: SQLiteIdentityRecordStore,
    *,
    current_session_id: str,
    replacement_credential: str,
    replacement_session: AuthSession,
    tenant_id: str,
    revoked_at: datetime,
) -> None:
    """Insert a replacement and revoke the current session in one transaction."""

    credential_hash = _credential_hash(replacement_credential)
    with store._connect() as connection:
        current = connection.execute(
            """SELECT user_id, tenant_id, status FROM sessions WHERE id = ?""",
            (current_session_id,),
        ).fetchone()
        if current is None:
            raise RuntimeError("Current session was not found.")
        if current["status"] != SessionStatus.active.value:
            raise RuntimeError("Current session is not active.")
        if current["user_id"] != replacement_session.user_id or current["tenant_id"] != tenant_id:
            raise RuntimeError("Replacement session scope does not match the current session.")

        connection.execute(
            """INSERT INTO sessions
            (id, credential_hash, user_id, tenant_id, status, issued_at, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                replacement_session.id,
                credential_hash,
                replacement_session.user_id,
                tenant_id,
                replacement_session.status.value,
                _timestamp(replacement_session.issued_at),
                _timestamp(replacement_session.expires_at),
                _timestamp(replacement_session.revoked_at),
            ),
        )
        cursor = connection.execute(
            """UPDATE sessions SET status = ?, revoked_at = ?
            WHERE id = ? AND status = ?""",
            (
                SessionStatus.revoked.value,
                _timestamp(revoked_at),
                current_session_id,
                SessionStatus.active.value,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Current session could not be revoked.")
