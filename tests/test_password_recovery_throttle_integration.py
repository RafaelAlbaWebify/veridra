from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.browser_auth_web import router as browser_auth_router
from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.password_recovery_api import PasswordResetDelivery
from veridra.password_recovery_api import router as recovery_api_router
from veridra.password_recovery_throttle import SQLitePasswordRecoveryThrottle

PASSWORD = "correct-horse-battery-staple"
ORIGIN = "http://testserver"
GENERIC_MESSAGE = "If an active account exists for that email, reset instructions have been sent."


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "identity.sqlite3"
    SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password=PASSWORD,
        confirmation=BOOTSTRAP_CONFIRMATION,
    )
    return database


def test_api_recovery_throttle_suppresses_delivery_without_changing_public_response(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    deliveries: list[PasswordResetDelivery] = []
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_password_reset_delivery = deliveries.append
    app.state.veridra_password_recovery_throttle = SQLitePasswordRecoveryThrottle(database)
    app.include_router(recovery_api_router)
    client = TestClient(app)

    existing = [
        client.post(
            "/api/auth/password-recovery/request",
            json={"email": "owner@example.com"},
        )
        for _ in range(4)
    ]
    missing = client.post(
        "/api/auth/password-recovery/request",
        json={"email": "missing@example.com"},
    )

    assert all(response.status_code == 202 for response in existing)
    assert missing.status_code == 202
    assert all(response.content == missing.content for response in existing)
    assert len(deliveries) == 3


def test_browser_recovery_throttle_keeps_generic_success_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database(tmp_path)
    deliveries: list[PasswordResetDelivery] = []
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_password_reset_delivery = deliveries.append
    app.state.veridra_password_recovery_throttle = SQLitePasswordRecoveryThrottle(database)
    app.include_router(browser_auth_router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    client = TestClient(app)

    responses = [
        client.post(
            "/forgot-password",
            headers={"Origin": ORIGIN},
            data={"email": "owner@example.com"},
        )
        for _ in range(4)
    ]

    assert all(response.status_code == 200 for response in responses)
    assert all(GENERIC_MESSAGE in response.text for response in responses)
    assert len(deliveries) == 3
