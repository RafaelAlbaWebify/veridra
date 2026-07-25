from __future__ import annotations

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
)
from .password_auth import SQLitePasswordAuthenticator, hash_password
from .sqlite_identity_store import SQLiteIdentityRecordStore

BOOTSTRAP_CONFIRMATION = "CREATE-FIRST-OWNER"


class IdentityBootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootstrapResult:
    tenant_id: str
    user_id: str
    tenant_slug: str
    email: str


class SQLiteIdentityBootstrap:
    def __init__(self, database: Path) -> None:
        self.database = database

    def initialize(self) -> None:
        SQLiteIdentityRecordStore(self.database).initialize()
        SQLitePasswordAuthenticator(self.database).initialize()

    def create_first_owner(
        self,
        *,
        tenant_slug: str,
        tenant_name: str,
        owner_email: str,
        owner_name: str,
        password: str,
        confirmation: str,
        created_at: datetime | None = None,
    ) -> BootstrapResult:
        if confirmation != BOOTSTRAP_CONFIRMATION:
            raise IdentityBootstrapError("Bootstrap confirmation token is invalid.")
        now = (created_at or datetime.now(UTC)).astimezone(UTC)
        tenant = Tenant.build(slug=tenant_slug, display_name=tenant_name, now=now)
        user = AuthenticatedUser.build(email=owner_email, display_name=owner_name, now=now).model_copy(
            update={"status": AccountStatus.active, "email_verified_at": now}
        )
        membership = TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=TenantRole.owner,
            active=True,
            created_at=now,
        )
        encoded_password = hash_password(password)
        self.initialize()
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            tenant_count = int(connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0])
            user_count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            if tenant_count or user_count:
                raise IdentityBootstrapError("Identity database has already been bootstrapped.")
            connection.execute(
                """INSERT INTO tenants (id, slug, display_name, status, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    tenant.id,
                    tenant.slug,
                    tenant.display_name,
                    tenant.status.value,
                    tenant.created_at.isoformat(),
                ),
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
            connection.execute(
                """INSERT INTO memberships (tenant_id, user_id, role, active, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    membership.tenant_id,
                    membership.user_id,
                    membership.role.value,
                    int(membership.active),
                    membership.created_at.isoformat(),
                ),
            )
            connection.execute(
                """INSERT INTO password_credentials (user_id, password_hash, updated_at)
                VALUES (?, ?, ?)""",
                (user.id, encoded_password, now.isoformat()),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return BootstrapResult(
            tenant_id=tenant.id,
            user_id=user.id,
            tenant_slug=tenant.slug,
            email=str(user.email),
        )
