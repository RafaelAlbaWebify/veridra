"""Canonical local loopback identity retains owner fallback and session integrity."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from veridra.application_identity import configure_identity_middleware
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore


def test_canonical_local_identity_uses_loopback_owner_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "identity.sqlite3"
    monkeypatch.setenv("VERIDRA_ENV", "local")
    monkeypatch.setenv("VERIDRA_IDENTITY_DB", str(database))
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://127.0.0.1:8011")
    monkeypatch.setenv("VERIDRA_BIND_HOST", "127.0.0.1")

    app = FastAPI()
    assert configure_identity_middleware(app) is True
    assert app.state.veridra_identity_database == database.resolve()
    assert isinstance(app.state.veridra_identity_store, SQLiteIdentityRecordStore)

    middleware = next(
        item for item in app.user_middleware
        if getattr(item.cls, "__name__", "") == "VerifiedIdentityMiddleware"
    )
    adapter = middleware.kwargs["adapter"]
    assert type(adapter).__name__ == "_SessionThenLocalOperatorAdapter"
    assert type(adapter.local_adapter).__name__ == "_LocalOperatorIdentityAdapter"
