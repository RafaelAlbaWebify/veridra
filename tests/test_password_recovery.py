from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.password_auth import SQLitePasswordAuthenticator
from veridra.password_recovery import PasswordRecoveryError, SQLitePasswordRecoveryService
from veridra.password_recovery_api import PasswordResetDelivery, router
from veridra.session_lifecycle import SessionLifecycleService
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
OLD_PASSWORD = "owner-correct-horse-battery"
NEW_PASSWORD = "replacement-correct-horse-battery"


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "identity.sqlite3"
    SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password=OLD_PASSWORD,
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    return database


def _client(database: Path, deliveries: list[PasswordResetDelivery]) -> TestClient:
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_password_reset_delivery = deliveries.append
    app.include_router(router)
    return TestClient(app, base_url="https://testserver")


def test_request_is_generic_and_delivers_only_for_existing_user(tmp_path: Path) -> None:
    database = _database(tmp_path)
    deliveries: list[PasswordResetDelivery] = []
    client = _client(database, deliveries)

    existing = client.post(
        "/api/auth/password-recovery/request",
        json={"email": "OWNER@EXAMPLE.COM"},
    )
    missing = client.post(
        "/api/auth/password-recovery/request",
        json={"email": "missing@example.com"},
    )

    assert existing.status_code == 202
    assert missing.status_code == 202
    assert existing.content == missing.content
    assert len(deliveries) == 1
    assert deliveries[0].email == "owner@example.com"
    assert deliveries[0].token.encode("utf-8") not in database.read_bytes()


def test_reset_changes_password_revokes_sessions_and_rejects_replay(tmp_path: Path) -> None:
    database = _database(tmp_path)
    authenticator = SQLitePasswordAuthenticator(database)
    records = authenticator.authenticate(
        email="owner@example.com",
        tenant_slug="customer-one",
        password=OLD_PASSWORD,
    )
    assert records is not None
    store = SQLiteIdentityRecordStore(database)
    issued_session = SessionLifecycleService(store, clock=lambda: NOW).issue(
        user_id=records.user.id,
        tenant_id=records.tenant.id,
        lifetime=timedelta(hours=1),
    )
    recovery = SQLitePasswordRecoveryService(database)
    issued_reset = recovery.issue(email="owner@example.com", now=NOW)
    assert issued_reset is not None

    recovery.reset_password(
        token=issued_reset.token,
        new_password=NEW_PASSWORD,
        now=NOW + timedelta(minutes=1),
    )

    assert authenticator.authenticate(
        email="owner@example.com",
        tenant_slug="customer-one",
        password=OLD_PASSWORD,
    ) is None
    assert authenticator.authenticate(
        email="owner@example.com",
        tenant_slug="customer-one",
        password=NEW_PASSWORD,
    ) is not None
    assert store._connect().execute(
        "SELECT status FROM sessions WHERE id = ?",
        (issued_session.session.id,),
    ).fetchone()["status"] == "revoked"
    with pytest.raises(PasswordRecoveryError, match="invalid"):
        recovery.reset_password(
            token=issued_reset.token,
            new_password=OLD_PASSWORD,
            now=NOW + timedelta(minutes=2),
        )


def test_new_request_invalidates_old_token_and_expiry_fails(tmp_path: Path) -> None:
    database = _database(tmp_path)
    recovery = SQLitePasswordRecoveryService(database)
    first = recovery.issue(email="owner@example.com", now=NOW)
    second = recovery.issue(email="owner@example.com", now=NOW + timedelta(minutes=1))
    assert first is not None
    assert second is not None

    with pytest.raises(PasswordRecoveryError, match="invalid"):
        recovery.reset_password(
            token=first.token,
            new_password=NEW_PASSWORD,
            now=NOW + timedelta(minutes=2),
        )

    expiring = recovery.issue(
        email="owner@example.com",
        now=NOW + timedelta(minutes=3),
        lifetime=timedelta(minutes=1),
    )
    assert expiring is not None
    with pytest.raises(PasswordRecoveryError, match="invalid"):
        recovery.reset_password(
            token=expiring.token,
            new_password=NEW_PASSWORD,
            now=NOW + timedelta(minutes=5),
        )
