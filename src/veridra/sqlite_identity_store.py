from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from .identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    AuthSession,
    SessionStatus,
    Tenant,
    TenantMembership,
    TenantRole,
    TenantStatus,
)
from .session_identity_adapter import IdentityRecordSet


class SQLiteIdentityStoreError(RuntimeError):
    pass


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _credential_hash(credential: str) -> str:
    if len(credential) < 32:
        raise SQLiteIdentityStoreError("Session credential is too short.")
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    email_verified_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    active INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    credential_hash TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    status TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (tenant_id, user_id) REFERENCES memberships(tenant_id, user_id)
);
CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_tenant_id_idx ON sessions(tenant_id);
"""


class SQLiteIdentityRecordStore:
    """Durable SQLite implementation of the server-side identity record contract.

    Opaque credentials are never stored directly. Each credential hash is bound to one
    user and one active tenant context so multi-membership users resolve deterministically.
    """

    def __init__(self, database: Path) -> None:
        self.database = database

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def save_tenant(self, tenant: Tenant) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO tenants (id, slug, display_name, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    slug=excluded.slug,
                    display_name=excluded.display_name,
                    status=excluded.status""",
                (
                    tenant.id,
                    tenant.slug,
                    tenant.display_name,
                    tenant.status.value,
                    _timestamp(tenant.created_at),
                ),
            )

    def save_user(self, user: AuthenticatedUser) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO users
                (id, email, display_name, status, email_verified_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    email=excluded.email,
                    display_name=excluded.display_name,
                    status=excluded.status,
                    email_verified_at=excluded.email_verified_at""",
                (
                    user.id,
                    str(user.email),
                    user.display_name,
                    user.status.value,
                    _timestamp(user.email_verified_at),
                    _timestamp(user.created_at),
                ),
            )

    def save_membership(self, membership: TenantMembership) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO memberships (tenant_id, user_id, role, active, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, user_id) DO UPDATE SET
                    role=excluded.role,
                    active=excluded.active""",
                (
                    membership.tenant_id,
                    membership.user_id,
                    membership.role.value,
                    int(membership.active),
                    _timestamp(membership.created_at),
                ),
            )

    def save_session(
        self,
        *,
        credential: str,
        tenant_id: str,
        session: AuthSession,
    ) -> None:
        credential_hash = _credential_hash(credential)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO sessions
                (id, credential_hash, user_id, tenant_id, status, issued_at, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    credential_hash=excluded.credential_hash,
                    user_id=excluded.user_id,
                    tenant_id=excluded.tenant_id,
                    status=excluded.status,
                    issued_at=excluded.issued_at,
                    expires_at=excluded.expires_at,
                    revoked_at=excluded.revoked_at""",
                (
                    session.id,
                    credential_hash,
                    session.user_id,
                    tenant_id,
                    session.status.value,
                    _timestamp(session.issued_at),
                    _timestamp(session.expires_at),
                    _timestamp(session.revoked_at),
                ),
            )

    def revoke_session(self, session_id: str, *, revoked_at: datetime) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE sessions
                SET status = ?, revoked_at = ?
                WHERE id = ?""",
                (SessionStatus.revoked.value, _timestamp(revoked_at), session_id),
            )
            if cursor.rowcount != 1:
                raise SQLiteIdentityStoreError("Session was not found.")

    async def load_by_credential(self, credential: str) -> IdentityRecordSet | None:
        try:
            credential_hash = _credential_hash(credential)
        except SQLiteIdentityStoreError:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """SELECT
                    u.id AS user_id, u.email, u.display_name AS user_display_name,
                    u.status AS user_status, u.email_verified_at, u.created_at AS user_created_at,
                    t.id AS tenant_id, t.slug, t.display_name AS tenant_display_name,
                    t.status AS tenant_status, t.created_at AS tenant_created_at,
                    m.role, m.active, m.created_at AS membership_created_at,
                    s.id AS session_id, s.status AS session_status, s.issued_at,
                    s.expires_at, s.revoked_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                JOIN tenants t ON t.id = s.tenant_id
                JOIN memberships m ON m.tenant_id = s.tenant_id AND m.user_id = s.user_id
                WHERE s.credential_hash = ?""",
                (credential_hash,),
            ).fetchone()
        if row is None:
            return None
        return IdentityRecordSet(
            user=AuthenticatedUser(
                id=row["user_id"],
                email=row["email"],
                display_name=row["user_display_name"],
                status=AccountStatus(row["user_status"]),
                email_verified_at=_datetime(row["email_verified_at"]),
                created_at=_datetime(row["user_created_at"]),
            ),
            tenant=Tenant(
                id=row["tenant_id"],
                slug=row["slug"],
                display_name=row["tenant_display_name"],
                status=TenantStatus(row["tenant_status"]),
                created_at=_datetime(row["tenant_created_at"]),
            ),
            membership=TenantMembership(
                tenant_id=row["tenant_id"],
                user_id=row["user_id"],
                role=TenantRole(row["role"]),
                active=bool(row["active"]),
                created_at=_datetime(row["membership_created_at"]),
            ),
            session=AuthSession(
                id=row["session_id"],
                user_id=row["user_id"],
                status=SessionStatus(row["session_status"]),
                issued_at=_datetime(row["issued_at"]),
                expires_at=_datetime(row["expires_at"]),
                revoked_at=_datetime(row["revoked_at"]),
            ),
        )
