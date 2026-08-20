from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .runtime_config import RuntimeConfig, RuntimeEnvironment

router = APIRouter(tags=["health"])


def _runtime(request: Request) -> RuntimeConfig | None:
    value = getattr(request.app.state, "veridra_runtime_config", None)
    return value if isinstance(value, RuntimeConfig) else None


def _identity_ready(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        connection.execute("SELECT 1").fetchone()
        required = {"tenants", "users", "memberships", "sessions"}
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        tables = {str(row[0]) for row in rows}
        return required.issubset(tables)
    except sqlite3.Error:
        return False
    finally:
        if connection is not None:
            connection.close()


def _tenant_root_ready(path: Path) -> bool:
    return (
        path.exists()
        and path.is_dir()
        and os.access(path, os.R_OK | os.W_OK | os.X_OK)
    )


@router.get("/health/live")
def health_live() -> JSONResponse:
    return JSONResponse(
        {"status": "ok"},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/health/ready")
def health_ready(request: Request) -> JSONResponse:
    runtime = _runtime(request)
    if runtime is None:
        return JSONResponse(
            {"status": "not_ready"},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    if runtime.environment is not RuntimeEnvironment.production:
        return JSONResponse(
            {"status": "ok"},
            headers={"Cache-Control": "no-store"},
        )

    identity = runtime.identity_database
    tenant_root = runtime.tenant_data_root
    ready = (
        identity is not None
        and tenant_root is not None
        and _identity_ready(identity)
        and _tenant_root_ready(tenant_root)
    )
    return JSONResponse(
        {"status": "ok" if ready else "not_ready"},
        status_code=200 if ready else 503,
        headers={"Cache-Control": "no-store"},
    )
