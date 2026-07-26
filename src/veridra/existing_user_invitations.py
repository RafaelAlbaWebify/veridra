from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .identity_tenancy import AccountStatus, TenantRole
from .tenant_invitations import (
    AcceptedInvitation,
    IssuedInvitation,
    SQLiteTenantInvitationService,
    TenantInvitationError,
)


class SQLiteExistingUserInvitationService:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.base = SQLiteTenantInvitationService(database)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _token_hash(token: str) -> str:
        if len(token) < 32:
            raise TenantInvitationError("Invitation token is invalid.")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

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
        self.base.initialize()
        try:
            with self._connect() as connection:
                user = connection.execute(
                    """SELECT id, status, email_verified_at
                    FROM users WHERE email = ?""",
                    (normalized_email,),
                ).fetchone()
                if (
                    user is None
                    or user["status"] != AccountStatus.active.value
                    or user["email_verified_at"] is None
                ):
                    raise TenantInvitationError(
                        "An active verified existing user was not found."
                    )
                membership = connection.execute(
                    """SELECT 1 FROM memberships
                    WHERE tenant_id = ? AND user_id = ?""",
                    (tenant_id, user["id"]),
                ).fetchone()
                if membership is not None:
                    raise TenantInvitationError(
                        "The user already belongs to this tenant."
                    )
                connection.execute(
                    """INSERT INTO tenant_invitations
                    (token_hash, tenant_id, email, role, created_by_user_id,
                     issued_at, expires_at, consumed_at)
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
            raise TenantInvitationError(
                "An active invitation already exists."
            ) from exc
        return IssuedInvitation(
            token=token,
            email=normalized_email,
            tenant_id=tenant_id,
            role=role,
            expires_at=expires_at,
        )

    def accept(
        self,
        *,
        token: str,
        user_id: str,
        now: datetime | None = None,
    ) -> AcceptedInvitation:
        accepted_at = (now or datetime.now(UTC)).astimezone(UTC)
        token_hash = self._token_hash(token)
        self.base.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            invitation = connection.execute(
                """SELECT tenant_id, email, role, expires_at, consumed_at
                FROM tenant_invitations WHERE token_hash = ?""",
                (token_hash,),
            ).fetchone()
            if invitation is None or invitation["consumed_at"] is not None:
                raise TenantInvitationError(
                    "Invitation is invalid or already used."
                )
            if datetime.fromisoformat(invitation["expires_at"]) <= accepted_at:
                raise TenantInvitationError("Invitation has expired.")
            user = connection.execute(
                """SELECT email, status, email_verified_at
                FROM users WHERE id = ?""",
                (user_id,),
            ).fetchone()
            if (
                user is None
                or user["status"] != AccountStatus.active.value
                or user["email_verified_at"] is None
                or user["email"] != invitation["email"]
            ):
                raise TenantInvitationError(
                    "Invitation does not match the authenticated account."
                )
            existing = connection.execute(
                """SELECT 1 FROM memberships
                WHERE tenant_id = ? AND user_id = ?""",
                (invitation["tenant_id"], user_id),
            ).fetchone()
            if existing is not None:
                raise TenantInvitationError(
                    "The user already belongs to this tenant."
                )
            role = TenantRole(invitation["role"])
            connection.execute(
                """INSERT INTO memberships
                (tenant_id, user_id, role, active, created_at)
                VALUES (?, ?, ?, 1, ?)""",
                (
                    invitation["tenant_id"],
                    user_id,
                    role.value,
                    accepted_at.isoformat(),
                ),
            )
            updated = connection.execute(
                """UPDATE tenant_invitations SET consumed_at = ?
                WHERE token_hash = ? AND consumed_at IS NULL""",
                (accepted_at.isoformat(), token_hash),
            )
            if updated.rowcount != 1:
                raise TenantInvitationError(
                    "Invitation was consumed concurrently."
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return AcceptedInvitation(
            user_id=user_id,
            tenant_id=invitation["tenant_id"],
            role=role,
        )
