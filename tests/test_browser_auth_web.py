from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.browser_auth_web import router
from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.login_throttle import SQLiteLoginThrottle
from veridra.password_auth import SQLitePasswordAuthenticator
from veridra.password_recovery_api import PasswordResetDelivery
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore

PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "new-correct-horse-battery-staple"
ORIGIN = "http://testserver"


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, list[PasswordResetDelivery], Path]:
    database = tmp_path / "identity.sqlite3"
    SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password=PASSWORD,
        confirmation=BOOTSTRAP_CONFIRMATION,
    )
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    authenticator = SQLitePasswordAuthenticator(database)
    authenticator.initialize()
    throttle = SQLiteLoginThrottle(database)
    throttle.initialize()
    deliveries: list[PasswordResetDelivery] = []

    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_identity_store = store
    app.state.veridra_password_authenticator = authenticator
    app.state.veridra_login_throttle = throttle
    app.state.veridra_password_reset_delivery = deliveries.append
    app.include_router(router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    return TestClient(app), deliveries, database


def test_login_page_is_browser_safe_and_links_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _client(tmp_path, monkeypatch)

    response = client.get("/login")

    assert response.status_code == 200
    assert "Sign in to Veridra" in response.text
    assert "name='tenant_slug'" in response.text
    assert "name='email'" in response.text
    assert "name='password'" in response.text
    assert "href='/forgot-password'" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"


def test_login_post_requires_same_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _client(tmp_path, monkeypatch)

    response = client.post(
        "/login",
        data={
            "tenant_slug": "customer-one",
            "email": "owner@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 403


def test_browser_login_rejects_invalid_credentials_and_issues_session_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _client(tmp_path, monkeypatch)
    headers = {"Origin": ORIGIN}

    invalid = client.post(
        "/login",
        headers=headers,
        data={
            "tenant_slug": "customer-one",
            "email": "owner@example.com",
            "password": "not-the-password",
        },
        follow_redirects=False,
    )
    valid = client.post(
        "/login",
        headers=headers,
        data={
            "tenant_slug": "customer-one",
            "email": "owner@example.com",
            "password": PASSWORD,
        },
        follow_redirects=False,
    )

    assert invalid.status_code == 401
    assert "Invalid login credentials" in invalid.text
    assert "set-cookie" not in invalid.headers
    assert valid.status_code == 303
    assert valid.headers["location"] == "/agency"
    cookie = valid.headers["set-cookie"]
    assert "veridra_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie


def test_forgot_password_keeps_existing_and_missing_accounts_indistinguishable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, deliveries, _ = _client(tmp_path, monkeypatch)
    headers = {"Origin": ORIGIN}

    existing = client.post(
        "/forgot-password",
        headers=headers,
        data={"email": "owner@example.com"},
    )
    missing = client.post(
        "/forgot-password",
        headers=headers,
        data={"email": "missing@example.com"},
    )

    assert existing.status_code == missing.status_code == 200
    expected = "If an active account exists for that email, reset instructions have been sent."
    assert expected in existing.text
    assert expected in missing.text
    assert len(deliveries) == 1
    assert deliveries[0].email == "owner@example.com"


def test_browser_reset_changes_password_revokes_token_and_supports_new_login(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, deliveries, _ = _client(tmp_path, monkeypatch)
    headers = {"Origin": ORIGIN}
    forgot = client.post(
        "/forgot-password",
        headers=headers,
        data={"email": "owner@example.com"},
    )
    assert forgot.status_code == 200
    token = deliveries[0].token

    reset_page = client.get("/reset-password", params={"token": token})
    mismatch = client.post(
        "/reset-password",
        headers=headers,
        data={
            "token": token,
            "new_password": NEW_PASSWORD,
            "password_confirm": "different-password-value",
        },
        follow_redirects=False,
    )
    reset = client.post(
        "/reset-password",
        headers=headers,
        data={
            "token": token,
            "new_password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
        follow_redirects=False,
    )
    reuse = client.post(
        "/reset-password",
        headers=headers,
        data={
            "token": token,
            "new_password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
        follow_redirects=False,
    )
    old_login = client.post(
        "/login",
        headers=headers,
        data={
            "tenant_slug": "customer-one",
            "email": "owner@example.com",
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    new_login = client.post(
        "/login",
        headers=headers,
        data={
            "tenant_slug": "customer-one",
            "email": "owner@example.com",
            "password": NEW_PASSWORD,
        },
        follow_redirects=False,
    )

    assert reset_page.status_code == 200
    assert token in reset_page.text
    assert reset_page.headers["cache-control"] == "no-store"
    assert reset_page.headers["referrer-policy"] == "no-referrer"
    assert mismatch.status_code == 400
    assert "Passwords do not match" in mismatch.text
    assert reset.status_code == 303
    assert reset.headers["location"] == "/login?reset=complete"
    assert reuse.status_code == 400
    assert "invalid or expired" in reuse.text
    assert old_login.status_code == 401
    assert new_login.status_code == 303
