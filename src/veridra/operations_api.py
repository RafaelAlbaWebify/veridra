from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["operations"])


class OperationalStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str


def _database_ready(database: Path | None) -> bool:
    if database is None:
        return True
    try:
        with sqlite3.connect(database) as connection:
            connection.execute("SELECT 1").fetchone()
    except (OSError, sqlite3.Error):
        return False
    return True


def _tenant_root_ready(root: Path | None) -> bool:
    if root is None:
        return True
    return root.exists() and root.is_dir()


@router.get("/health", response_model=OperationalStatus)
def health() -> OperationalStatus:
    return OperationalStatus(status="ok")


@router.get("/ready", response_model=OperationalStatus)
def ready(request: Request, response: Response) -> OperationalStatus:
    database = getattr(request.app.state, "veridra_identity_database", None)
    tenant_root = getattr(request.app.state, "veridra_tenant_data_root", None)
    if not isinstance(database, Path):
        database = None
    if not isinstance(tenant_root, Path):
        tenant_root = None
    if not _database_ready(database) or not _tenant_root_ready(tenant_root):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return OperationalStatus(status="unavailable")
    return OperationalStatus(status="ready")
