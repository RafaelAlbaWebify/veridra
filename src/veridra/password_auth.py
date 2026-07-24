from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    Tenant,
    TenantMembership,
    TenantRole,
    TenantStatus,
)

_SCRYPT_N = 1 << 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_MAXMEM = 64 * 1024 * 1024
_SALT_BYTES = 16
_DUMMY_SALT = bytes.fromhex("e4098cf76d940a693f269a98c76b7a61")


class PasswordAuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PasswordLoginRecords:
    user: AuthenticatedUser
    tenant: Tenant
    membership: TenantMembership
    password_hash: str


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Password length must be between 12 and 1024 characters.")
    resolved_salt = salt or os.urandom(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=resolved_salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    parameters = f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}"
    return f"{parameters}${_b64encode(resolved_salt)}${_b64encode(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, salt_text, hash_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        expected = _b64decode(hash_text)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt_text),
            n=int(n_text),
            r=int(r_text),
            p=int(p_text),
            dklen=len(expected),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


_DUMMY_HASH = hash_password("not-a-real-user-password", salt=_DUMMY_SALT)


class SQLitePasswordAuthenticator:
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
                """CREATE TABLE IF NOT EXISTS password_credentials (
                    user_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )"""
            )

    def set_password(
        self,
        user_id: str,
        password: str,
        *,
        updated_at: datetime | None = None,
    ) -> None:
        encoded = hash_password(password)
        timestamp = (updated_at or datetime.now(UTC)).astimezone(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO password_credentials (user_id, password_hash, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    password_hash=excluded.password_hash,
                    updated_at=excluded.updated_at""",
                (user_id, encoded, timestamp),
            )

    def authenticate(
        self,
        *,
        email: str,
        tenant_slug: str,
        password: str,
    ) -> PasswordLoginRecords | None:
        normalized_email = email.strip().lower()
        normalized_tenant = tenant_slug.strip().lower()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT
                    u.id AS user_id, u.email, u.display_name AS user_display_name,
                    u.status AS user_status, u.email_verified_at,
                    u.created_at AS user_created_at,
                    t.id AS tenant_id, t.slug, t.display_name AS tenant_display_name,
                    t.status AS tenant_status, t.created_at AS tenant_created_at,
                    m.role, m.active, m.created_at AS membership_created_at,
                    c.password_hash
                FROM users u
                JOIN memberships m ON m.user_id = u.id
                JOIN tenants t ON t.id = m.tenant_id
                JOIN password_credentials c ON c.user_id = u.id
                WHERE u.email = ? AND t.slug = ?""",
                (normalized_email, normalized_tenant),
            ).fetchone()
        encoded = row["password_hash"] if row is not None else _DUMMY_HASH
        valid_password = verify_password(password, encoded)
        if row is None or not valid_password:
            return None
        user = AuthenticatedUser(
            id=row["user_id"],
            email=row["email"],
            display_name=row["user_display_name"],
            status=AccountStatus(row["user_status"]),
            email_verified_at=datetime.fromisoformat(row["email_verified_at"])
            if row["email_verified_at"]
            else None,
            created_at=datetime.fromisoformat(row["user_created_at"]),
        )
        tenant = Tenant(
            id=row["tenant_id"],
            slug=row["slug"],
            display_name=row["tenant_display_name"],
            status=TenantStatus(row["tenant_status"]),
            created_at=datetime.fromisoformat(row["tenant_created_at"]),
        )
        membership = TenantMembership(
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            role=TenantRole(row["role"]),
            active=bool(row["active"]),
            created_at=datetime.fromisoformat(row["membership_created_at"]),
        )
        if (
            user.status is not AccountStatus.active
            or user.email_verified_at is None
            or tenant.status is not TenantStatus.active
            or not membership.active
        ):
            return None
        return PasswordLoginRecords(
            user=user,
            tenant=tenant,
            membership=membership,
            password_hash=encoded,
        )
