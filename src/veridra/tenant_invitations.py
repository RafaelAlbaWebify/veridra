from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from .identity_tenancy import AccountStatus, AuthenticatedUser, TenantRole
from .password_auth import hash_password


class TenantInvitationError(RuntimeError):
    pass


@dataclass(frozen=True)
class IssuedInvitation:
    token: str
    email: str
    tenant_id: str
    role: TenantRole
    expires_at: datetime


@dataclass(frozen=True)
class InvitationSummary:
    id: str
    email: str
    tenant_id: str
    role: TenantRole
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class AcceptedInvitation:
    user_id: str
    tenant_id: str
    role: TenantRole


class SQLiteTenantInvitationService:
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
                """CREATE TABLE IF NOT EXISTS tenant_invitations (
                    token_hash TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_by_user_id TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
                )"""
            )
            connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS active_invitation_email_idx
                ON tenant_invitations(tenant_id, email)
                WHERE consumed_at IS NULL"""
            )

    @staticmethod
    def _token_hash(token: str) -> str:
        if len(token) < 32:
            raise TenantInvitationError("Invitation token is invalid.")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _management_id(token_hash: str) -> str:
        return hashlib.sha256(f"invitation-management:{token_hash}".encode()).hexdigest()[:24]

    @staticmethod
    def _issued_from_row(*, token: str, row: sqlite3.Row) -> IssuedInvitation:
        return IssuedInvitation(
            token=token,
            email=row["email"],
            tenant_id=row["tenant_id"],
            role=TenantRole(row["role"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
        )

    def issue(
        self,
        *,
        tenant_id: str,
        created_by_user_id: str,
        email: str,
        role: TenantRole,
        now: datetime | None = None,
        lifetime: timedelta = timedelta(hours=48),
    ) -> IssuedInvitation:
        if role is TenantRole.owner:
            raise TenantInvitationError("Owner invitations are not permitted.")
        if lifetime <= timedelta(0):
            raise TenantInvitationError("Invitation lifetime must be positive.")
        issued_at = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = issued_at + lifetime
        normalized_email = email.strip().lower()
        token = secrets.token_urlsafe(32)
        token_hash = self._token_hash(token)
        self.initialize()
        try:
            with self._connect() as connection:
                existing_user = connection.execute(
                    "SELECT 1 FROM users WHERE email = ?",
                    (normalized_email,),
                ).fetchone()
                if existing_user is not None:
                    raise TenantInvitationError(
                        "Existing users must join a tenant through an authenticated flow."
                    )
                connection.execute(
                    """INSERT INTO tenant_invitations
                    (token_hash, tenant_id, email, role, created_by_user_id, issued_at,
                     expires_at, consumed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                    (
                        token_hash,
                        tenant_id,
                        normalized_email,
                        role.value,
                        created_by_user_id,
                        issued_at.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise TenantInvitationError("An active invitation already exists.") from exc
        return IssuedInvitation(
            token=token,
            email=normalized_email,
            tenant_id=tenant_id,
            role=role,
            expires_at=expires_at,
        )

    def list_active(
        self,
        *,
        tenant_id: str,
        now: datetime | None = None,
    ) -> tuple[InvitationSummary, ...]:
        checked_at = (now or datetime.now(UTC)).astimezone(UTC)
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT token_hash, tenant_id, email, role, issued_at, expires_at
                FROM tenant_invitations
                WHERE tenant_id = ? AND consumed_at IS NULL AND expires_at > ?
                ORDER BY issued_at, email""",
                (tenant_id, checked_at.isoformat()),
            ).fetchall()
        return tuple(
            InvitationSummary(
                id=self._management_id(row["token_hash"]),
                email=row["email"],
                tenant_id=row["tenant_id"],
                role=TenantRole(row["role"]),
                issued_at=datetime.fromisoformat(row["issued_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
            )
            for row in rows
        )

    def _active_row(
        self,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        invitation_id: str,
        now: datetime,
    ) -> sqlite3.Row:
        rows = connection.execute(
            """SELECT token_hash, tenant_id, email, role, created_by_user_id,
                      issued_at, expires_at
            FROM tenant_invitations
            WHERE tenant_id = ? AND consumed_at IS NULL AND expires_at > ?""",
            (tenant_id, now.isoformat()),
        ).fetchall()
        for row in rows:
            if self._management_id(row["token_hash"]) == invitation_id:
                return cast(sqlite3.Row, row)
        raise TenantInvitationError("Invitation was not found.")

    def cancel(
        self,
        *,
        tenant_id: str,
        invitation_id: str,
        now: datetime | None = None,
    ) -> None:
        cancelled_at = (now or datetime.now(UTC)).astimezone(UTC)
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._active_row(
                connection,
                tenant_id=tenant_id,
                invitation_id=invitation_id,
                now=cancelled_at,
            )
            updated = connection.execute(
                """UPDATE tenant_invitations SET consumed_at = ?
                WHERE token_hash = ? AND consumed_at IS NULL""",
                (cancelled_at.isoformat(), row["token_hash"]),
            )
            if updated.rowcount != 1:
                raise TenantInvitationError("Invitation changed concurrently.")

    def resend(
        self,
        *,
        tenant_id: str,
        invitation_id: str,
        created_by_user_id: str,
        now: datetime | None = None,
        lifetime: timedelta = timedelta(hours=48),
    ) -> IssuedInvitation:
        if lifetime <= timedelta(0):
            raise TenantInvitationError("Invitation lifetime must be positive.")
        issued_at = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = issued_at + lifetime
        token = secrets.token_urlsafe(32)
        token_hash = self._token_hash(token)
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._active_row(
                connection,
                tenant_id=tenant_id,
                invitation_id=invitation_id,
                now=issued_at,
            )
            updated = connection.execute(
                """UPDATE tenant_invitations SET consumed_at = ?
                WHERE token_hash = ? AND consumed_at IS NULL""",
                (issued_at.isoformat(), row["token_hash"]),
            )
            if updated.rowcount != 1:
                raise TenantInvitationError("Invitation changed concurrently.")
            connection.execute(
                """INSERT INTO tenant_invitations
                (token_hash, tenant_id, email, role, created_by_user_id, issued_at,
                 expires_at, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                (
                    token_hash,
                    tenant_id,
                    row["email"],
                    row["role"],
                    created_by_user_id,
                    issued_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return IssuedInvitation(
            token=token,
            email=row["email"],
            tenant_id=tenant_id,
            role=TenantRole(row["role"]),
            expires_at=expires_at,
        )

    def accept(
        self,
        *,
        token: str,
        display_name: str,
        password: str,
        now: datetime | None = None,
    ) -> AcceptedInvitation:
        accepted_at = (now or datetime.now(UTC)).astimezone(UTC)
        token_hash = self._token_hash(token)
        encoded_password = hash_password(password)
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT tenant_id, email, role, expires_at, consumed_at
                FROM tenant_invitations WHERE token_hash = ?""",
                (token_hash,),
            ).fetchone()
            if row is None or row["consumed_at"] is not None:
                raise TenantInvitationError("Invitation is invalid or already used.")
            if datetime.fromisoformat(row["expires_at"]) <= accepted_at:
                raise TenantInvitationError("Invitation has expired.")
            existing_user = connection.execute(
                "SELECT 1 FROM users WHERE email = ?",
                (row["email"],),
            ).fetchone()
            if existing_user is not None:
                raise TenantInvitationError("Invitation cannot create this account.")
            user = AuthenticatedUser.build(
                email=row["email"],
                display_name=display_name,
                now=accepted_at,
            ).model_copy(
                update={"status": AccountStatus.active, "email_verified_at": accepted_at}
            )
            connection.execute(
                """INSERT INTO users
                (id, email, display_name, status, email_verified_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user.id,
                    str(user.email),
                    user.display_name,
                    user.status.value,
                    user.email_verified_at.isoformat() if user.email_verified_at else None,
                    user.created_at.isoformat(),
                ),
            )
            role = TenantRole(row["role"])
            connection.execute(
                """INSERT INTO memberships (tenant_id, user_id, role, active, created_at)
                VALUES (?, ?, ?, 1, ?)""",
                (row["tenant_id"], user.id, role.value, accepted_at.isoformat()),
            )
            connection.execute(
                """INSERT INTO password_credentials (user_id, password_hash, updated_at)
                VALUES (?, ?, ?)""",
                (user.id, encoded_password, accepted_at.isoformat()),
            )
            updated = connection.execute(
                """UPDATE tenant_invitations SET consumed_at = ?
                WHERE token_hash = ? AND consumed_at IS NULL""",
                (accepted_at.isoformat(), token_hash),
            )
            if updated.rowcount != 1:
                raise TenantInvitationError("Invitation was consumed concurrently.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return AcceptedInvitation(user_id=user.id, tenant_id=row["tenant_id"], role=role)
