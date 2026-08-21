from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    Tenant,
    TenantMembership,
    TenantRole,
)
from .password_auth import hash_password
from .workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore


class TenantSignupError(RuntimeError):
    pass


class TenantSignupSlugUnavailable(TenantSignupError):
    pass


@dataclass(frozen=True)
class IssuedTenantSignup:
    token: str
    email: str
    expires_at: datetime


@dataclass(frozen=True)
class AcceptedTenantSignup:
    tenant_id: str
    user_id: str


class SQLiteTenantSignupService:
    _MAX_EMAIL_REQUESTS = 3
    _MAX_GLOBAL_REQUESTS = 30
    _REQUEST_WINDOW = timedelta(minutes=15)

    def __init__(self, database: Path, tenant_data_root: Path) -> None:
        self.database = database
        self.tenant_data_root = tenant_data_root

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS tenant_signup_requests (
                    token_hash TEXT PRIMARY KEY,
                    tenant_slug TEXT NOT NULL,
                    tenant_name TEXT NOT NULL,
                    owner_email TEXT NOT NULL,
                    owner_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS tenant_signup_requests_email_idx
                ON tenant_signup_requests(owner_email, issued_at)"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS tenant_signup_requests_expiry_idx
                ON tenant_signup_requests(expires_at)"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS tenant_signup_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_hash TEXT NOT NULL,
                    attempted_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS tenant_signup_attempts_email_idx
                ON tenant_signup_attempts(email_hash, attempted_at)"""
            )

    @staticmethod
    def _token_hash(token: str) -> str:
        if len(token) < 32:
            raise TenantSignupError("Signup verification token is invalid.")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _email_hash(email: str) -> str:
        return hashlib.sha256(email.encode("utf-8")).hexdigest()

    def _reserve_attempt(
        self,
        *,
        tenant: Tenant,
        user: AuthenticatedUser,
        issued_at: datetime,
    ) -> bool:
        email = str(user.email)
        email_hash = self._email_hash(email)
        cutoff = issued_at - self._REQUEST_WINDOW
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM tenant_signup_requests WHERE expires_at <= ?",
                (issued_at.isoformat(),),
            )
            connection.execute(
                "DELETE FROM tenant_signup_attempts WHERE attempted_at < ?",
                (cutoff.isoformat(),),
            )
            if connection.execute(
                "SELECT 1 FROM tenants WHERE slug = ?",
                (tenant.slug,),
            ).fetchone() is not None:
                raise TenantSignupSlugUnavailable("Workspace slug is already in use.")
            if connection.execute(
                "SELECT 1 FROM users WHERE email = ?",
                (email,),
            ).fetchone() is not None:
                connection.rollback()
                return False
            email_attempts = int(
                connection.execute(
                    "SELECT COUNT(*) FROM tenant_signup_attempts WHERE email_hash = ?",
                    (email_hash,),
                ).fetchone()[0]
            )
            global_attempts = int(
                connection.execute("SELECT COUNT(*) FROM tenant_signup_attempts").fetchone()[0]
            )
            if (
                email_attempts >= self._MAX_EMAIL_REQUESTS
                or global_attempts >= self._MAX_GLOBAL_REQUESTS
            ):
                connection.rollback()
                return False
            connection.execute(
                "INSERT INTO tenant_signup_attempts (email_hash, attempted_at) VALUES (?, ?)",
                (email_hash, issued_at.isoformat()),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def issue(
        self,
        *,
        tenant_slug: str,
        tenant_name: str,
        owner_email: str,
        owner_name: str,
        password: str,
        now: datetime | None = None,
        lifetime: timedelta = timedelta(minutes=30),
    ) -> IssuedTenantSignup | None:
        if lifetime <= timedelta(0):
            raise ValueError("Signup verification lifetime must be positive.")
        issued_at = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = issued_at + lifetime
        tenant = Tenant.build(slug=tenant_slug, display_name=tenant_name, now=issued_at)
        user = AuthenticatedUser.build(email=owner_email, display_name=owner_name, now=issued_at)
        self.initialize()
        if not self._reserve_attempt(tenant=tenant, user=user, issued_at=issued_at):
            return None

        encoded_password = hash_password(password)
        token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(token)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM tenants WHERE slug = ?",
                (tenant.slug,),
            ).fetchone() is not None:
                raise TenantSignupSlugUnavailable("Workspace slug is already in use.")
            if connection.execute(
                "SELECT 1 FROM users WHERE email = ?",
                (str(user.email),),
            ).fetchone() is not None:
                connection.rollback()
                return None
            connection.execute(
                """INSERT INTO tenant_signup_requests
                (token_hash, tenant_slug, tenant_name, owner_email, owner_name,
                 password_hash, issued_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    token_hash,
                    tenant.slug,
                    tenant.display_name,
                    str(user.email),
                    user.display_name,
                    encoded_password,
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
        return IssuedTenantSignup(
            token=token,
            email=str(user.email),
            expires_at=expires_at,
        )

    def cancel(self, token: str) -> None:
        token_hash = self._token_hash(token)
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM tenant_signup_requests WHERE token_hash = ?",
                    (token_hash,),
                )
        except sqlite3.Error as exc:
            raise TenantSignupError("Pending signup could not be discarded safely.") from exc

    def is_valid(self, token: str, *, now: datetime | None = None) -> bool:
        checked_at = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            token_hash = self._token_hash(token)
        except TenantSignupError:
            return False
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT expires_at FROM tenant_signup_requests WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        return row is not None and datetime.fromisoformat(row["expires_at"]) > checked_at

    def accept(
        self,
        *,
        token: str,
        now: datetime | None = None,
    ) -> AcceptedTenantSignup:
        accepted_at = (now or datetime.now(UTC)).astimezone(UTC)
        token_hash = self._token_hash(token)
        self.initialize()
        connection = self._connect()
        workspace_path: Path | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM tenant_signup_requests WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None or datetime.fromisoformat(row["expires_at"]) <= accepted_at:
                raise TenantSignupError("Signup verification token is invalid or expired.")
            tenant = Tenant.build(
                slug=row["tenant_slug"],
                display_name=row["tenant_name"],
                now=accepted_at,
            )
            user = AuthenticatedUser.build(
                email=row["owner_email"],
                display_name=row["owner_name"],
                now=accepted_at,
            ).model_copy(
                update={
                    "status": AccountStatus.active,
                    "email_verified_at": accepted_at,
                }
            )
            membership = TenantMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                role=TenantRole.owner,
                active=True,
                created_at=accepted_at,
            )
            if connection.execute(
                "SELECT 1 FROM tenants WHERE slug = ?",
                (tenant.slug,),
            ).fetchone() is not None:
                raise TenantSignupError("Signup verification token is no longer available.")
            if connection.execute(
                "SELECT 1 FROM users WHERE email = ?",
                (str(user.email),),
            ).fetchone() is not None:
                raise TenantSignupError("Signup verification token is no longer available.")

            workspace_store = WorkspaceStore(self.tenant_data_root / tenant.id / "workspace")
            workspace_path = workspace_store.path
            workspace_store.save(
                WorkspaceConfig(display_name=tenant.display_name, plan=PlanName.free)
            )
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
                    accepted_at.isoformat(),
                    user.created_at.isoformat(),
                ),
            )
            connection.execute(
                """INSERT INTO memberships (tenant_id, user_id, role, active, created_at)
                VALUES (?, ?, ?, 1, ?)""",
                (
                    membership.tenant_id,
                    membership.user_id,
                    membership.role.value,
                    membership.created_at.isoformat(),
                ),
            )
            connection.execute(
                """INSERT INTO password_credentials (user_id, password_hash, updated_at)
                VALUES (?, ?, ?)""",
                (user.id, row["password_hash"], accepted_at.isoformat()),
            )
            deleted = connection.execute(
                "DELETE FROM tenant_signup_requests WHERE token_hash = ?",
                (token_hash,),
            )
            if deleted.rowcount != 1:
                raise TenantSignupError("Signup verification changed concurrently.")
            connection.commit()
            return AcceptedTenantSignup(tenant_id=tenant.id, user_id=user.id)
        except Exception:
            connection.rollback()
            if workspace_path is not None:
                workspace_path.unlink(missing_ok=True)
            raise
        finally:
            connection.close()
