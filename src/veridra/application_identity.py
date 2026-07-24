from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from .identity_middleware import VerifiedIdentityMiddleware
from .session_cookie import SecureSessionCookieExtractor
from .session_identity_adapter import ServerSideSessionIdentityAdapter
from .sqlite_identity_store import SQLiteIdentityRecordStore


def configure_identity_middleware(app: FastAPI) -> bool:
    """Install durable cookie-session identity resolution when explicitly configured."""

    configured_database = os.environ.get("VERIDRA_IDENTITY_DB")
    if not configured_database:
        return False

    database = Path(configured_database).expanduser().resolve()
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    adapter = ServerSideSessionIdentityAdapter(
        extractor=SecureSessionCookieExtractor(),
        store=store,
    )
    app.add_middleware(VerifiedIdentityMiddleware, adapter=adapter)
    return True
