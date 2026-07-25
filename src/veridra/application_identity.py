from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from .identity_middleware import VerifiedIdentityMiddleware
from .login_throttle import SQLiteLoginThrottle
from .password_auth import SQLitePasswordAuthenticator
from .session_cookie import SecureSessionCookieExtractor
from .session_identity_adapter import ServerSideSessionIdentityAdapter
from .sqlite_identity_store import SQLiteIdentityRecordStore
from .sqlite_schema_versions import SQLiteSchemaVersionManager


def configure_identity_middleware(app: FastAPI) -> bool:
    """Install durable cookie-session identity resolution when explicitly configured."""

    configured_database = os.environ.get("VERIDRA_IDENTITY_DB")
    if not configured_database:
        return False

    database = Path(configured_database).expanduser().resolve()
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    SQLiteSchemaVersionManager(database).apply_all()
    password_authenticator = SQLitePasswordAuthenticator(database)
    password_authenticator.initialize()
    login_throttle = SQLiteLoginThrottle(database)
    login_throttle.initialize()
    app.state.veridra_identity_database = database
    app.state.veridra_identity_store = store
    app.state.veridra_password_authenticator = password_authenticator
    app.state.veridra_login_throttle = login_throttle
    adapter = ServerSideSessionIdentityAdapter(
        extractor=SecureSessionCookieExtractor(),
        store=store,
    )
    app.add_middleware(VerifiedIdentityMiddleware, adapter=adapter)
    return True
