from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from veridra.auth_api import router as auth_router
from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    Tenant,
    TenantMembership,
    TenantRole,
)
from veridra.login_throttle import SQLiteLoginThrottle
from veridra.password_auth import SQLitePasswordAuthenticator
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore

NOW = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery-staple"


def test_throttle_persists_and_expires_without_raw_identity(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    throttle = SQLiteLoginThrottle(
        database,
        max_failures=2,
        failure_window=timedelta(minutes=10),
        lockout_duration=timedelta(minutes=5),
    )
    throttle.initialize()

    first = throttle.record_failure(
        email="Owner@Example.com",
        tenant_slug="customer-one",
        now=NOW,
    )
    locked = throttle.record_failure(
        email="owner@example.com",
        tenant_slug="customer-one",
        now=NOW + timedelta(seconds=1),
    )
    reloaded = SQLiteLoginThrottle(database)

    assert first.allowed
    assert not locked.allowed
    assert not reloaded.check(
        email="owner@example.com",
        tenant_slug="customer-one",
        now=NOW + timedelta(minutes=1),
    ).allowed
    assert reloaded.check(
        email="owner@example.com",
        tenant_slug="customer-one",
        now=NOW + timedelta(minutes=6),
    ).allowed
    assert b"owner@example.com" not in database.read_bytes()


def test_throttle_keys_each_tenant_separately(tmp_path: Path) -> None:
    throttle = SQLiteLoginThrottle(tmp_path / "identity.sqlite3", max_failures=1)
    throttle.initialize()

    throttle.record_failure(email="owner@example.com", tenant_slug="tenant-one", now=NOW)

    assert not throttle.check(
        email="owner@example.com", tenant_slug="tenant-one", now=NOW
    ).allowed
    assert throttle.check(
        email="owner@example.com", tenant_slug="tenant-two", now=NOW
    ).allowed


def _client(tmp_path: Path) -> TestClient:
    database = tmp_path / "identity.sqlite3"
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    authenticator = SQLitePasswordAuthenticator(database)
    authenticator.initialize()
    throttle = SQLiteLoginThrottle(database)
    throttle.initialize()
    tenant = Tenant.build(slug="customer-one", display_name="Customer one", now=NOW)
    user = AuthenticatedUser.build(
        email="owner@example.com",
        display_name="Owner",
        now=NOW,
    ).model_copy(update={"status": AccountStatus.active, "email_verified_at": NOW})
    store.save_tenant(tenant)
    store.save_user(user)
    store.save_membership(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=TenantRole.owner,
            created_at=NOW,
        )
    )
    authenticator.set_password(user.id, PASSWORD, updated_at=NOW)
    app = FastAPI()
    app.state.veridra_identity_store = store
    app.state.veridra_password_authenticator = authenticator
    app.state.veridra_login_throttle = throttle
    app.include_router(auth_router)
    return TestClient(app, base_url="https://testserver")


def _login(client: TestClient, password: str) -> Response:
    return cast(
        Response,
        client.post(
            "/api/auth/login",
            json={
                "email": "owner@example.com",
                "tenant_slug": "customer-one",
                "password": password,
            },
        ),
    )


def test_fifth_failure_locks_and_success_resets_counter(tmp_path: Path) -> None:
    client = _client(tmp_path)

    for _ in range(4):
        assert _login(client, "wrong-password-value").status_code == 401
    assert _login(client, PASSWORD).status_code == 200
    client.cookies.clear()
    for _ in range(4):
        assert _login(client, "wrong-password-value").status_code == 401

    locked = _login(client, "wrong-password-value")

    assert locked.status_code == 429
    assert locked.json() == {"detail": "Too many login attempts. Try again later."}
    assert int(locked.headers["retry-after"]) > 0
    assert _login(client, PASSWORD).status_code == 429
