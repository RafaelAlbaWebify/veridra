from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path

from fastapi import FastAPI, Request

from .identity_middleware import VerifiedIdentityMiddleware
from .identity_tenancy import RequestIdentity, TenantRole
from .login_throttle import SQLiteLoginThrottle
from .password_auth import SQLitePasswordAuthenticator
from .password_recovery_throttle import SQLitePasswordRecoveryThrottle
from .runtime_config import local_agency_mode_enabled
from .same_origin import SameOriginConfigurationError, TrustedSameOriginPolicy
from .session_cookie import SecureSessionCookieExtractor
from .session_identity_adapter import ServerSideSessionIdentityAdapter
from .sqlite_identity_store import SQLiteIdentityRecordStore
from .sqlite_schema_versions import SQLiteSchemaVersionManager


class _LocalOperatorIdentityAdapter:
    """Resolve the single loopback owner without a browser login in local modes."""

    def __init__(self, database: Path) -> None:
        self.database = database

    async def resolve(self, request: Request) -> RequestIdentity | None:
        operator_mode = os.environ.get("VERIDRA_ENV", "").strip().lower() == "operator"
        if not operator_mode and not local_agency_mode_enabled():
            return None
        bind_host = os.environ.get("VERIDRA_BIND_HOST", "127.0.0.1").strip()
        try:
            if not ip_address(bind_host).is_loopback:
                return None
        except ValueError:
            return None

        client_host = request.client.host if request.client is not None else ""
        try:
            if not client_host or not ip_address(client_host).is_loopback:
                return None
        except ValueError:
            return None

        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT u.id AS user_id, t.id AS tenant_id, m.role
                FROM memberships m
                JOIN users u ON u.id = m.user_id
                JOIN tenants t ON t.id = m.tenant_id
                WHERE m.active = 1
                  AND u.status = 'active'
                  AND u.email_verified_at IS NOT NULL
                  AND t.status = 'active'
                  AND m.role = ?
                ORDER BY t.created_at, u.created_at""",
                (TenantRole.owner.value,),
            ).fetchall()

        if len(rows) != 1:
            return None

        row = rows[0]
        return RequestIdentity(
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            membership_role=TenantRole(row["role"]),
            session_id="local-operator-loopback-session",
            authenticated_at=datetime.now(UTC),
        )


class _SessionThenLocalOperatorAdapter:
    def __init__(
        self,
        session_adapter: ServerSideSessionIdentityAdapter,
        local_adapter: _LocalOperatorIdentityAdapter,
    ) -> None:
        self.session_adapter = session_adapter
        self.local_adapter = local_adapter

    async def resolve(self, request: Request) -> RequestIdentity | None:
        session_identity = await self.session_adapter.resolve(request)
        if session_identity is not None:
            return session_identity
        return await self.local_adapter.resolve(request)


def configure_identity_middleware(app: FastAPI) -> bool:
    """Install durable cookie-session identity resolution when explicitly configured."""

    configured_database = os.environ.get("VERIDRA_IDENTITY_DB")
    if not configured_database:
        return False
    configured_origin = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured_origin:
        raise SameOriginConfigurationError(
            "VERIDRA_TRUSTED_ORIGIN is required when cookie authentication is enabled."
        )

    database = Path(configured_database).expanduser().resolve()
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    SQLiteSchemaVersionManager(database).apply_all()
    app.state.veridra_identity_database = database
    app.state.veridra_identity_store = store

    operator_mode = os.environ.get("VERIDRA_ENV", "").strip().lower() == "operator"
    if operator_mode:
        adapter = _LocalOperatorIdentityAdapter(database)
    else:
        password_authenticator = SQLitePasswordAuthenticator(database)
        password_authenticator.initialize()
        login_throttle = SQLiteLoginThrottle(database)
        login_throttle.initialize()
        recovery_throttle = SQLitePasswordRecoveryThrottle(database)
        recovery_throttle.initialize()
        app.state.veridra_password_authenticator = password_authenticator
        app.state.veridra_login_throttle = login_throttle
        app.state.veridra_password_recovery_throttle = recovery_throttle
        session_adapter = ServerSideSessionIdentityAdapter(
            extractor=SecureSessionCookieExtractor(),
            store=store,
        )
        adapter = _SessionThenLocalOperatorAdapter(
            session_adapter,
            _LocalOperatorIdentityAdapter(database),
        )

    app.add_middleware(
        VerifiedIdentityMiddleware,
        adapter=adapter,
        same_origin_policy=TrustedSameOriginPolicy(configured_origin),
    )
    return True
