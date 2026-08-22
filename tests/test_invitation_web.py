from __future__ import annotations

import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.browser_auth_web import router as browser_auth_router
from veridra.existing_user_invitations import SQLiteExistingUserInvitationService
from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.invitation_web import router as invitation_router
from veridra.login_throttle import SQLiteLoginThrottle
from veridra.password_auth import SQLitePasswordAuthenticator
from veridra.request_security import bind_verified_request_identity
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.tenant_invitations import SQLiteTenantInvitationService

NOW = datetime.now(UTC).replace(microsecond=0)
ORIGIN = "http://testserver"
OWNER_PASSWORD = "owner-correct-horse-battery"
INVITEE_PASSWORD = "invitee-correct-horse-battery"


def _base(tmp_path: Path) -> tuple[Path, str, str]:
    database = tmp_path / "identity.sqlite3"
    created = SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer One",
        owner_email="owner@example.com",
        owner_name="Owner",
        password=OWNER_PASSWORD,
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    return database, created.tenant_id, created.user_id


def _app(database: Path) -> FastAPI:
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    authenticator = SQLitePasswordAuthenticator(database)
    authenticator.initialize()
    throttle = SQLiteLoginThrottle(database)
    throttle.initialize()
    app = FastAPI()
    app.state.veridra_identity_database = database
    app.state.veridra_identity_store = store
    app.state.veridra_password_authenticator = authenticator
    app.state.veridra_login_throttle = throttle
    app.include_router(browser_auth_router)
    app.include_router(invitation_router)
    return app


def test_new_user_accepts_invitation_in_browser_and_gets_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, tenant_id, owner_id = _base(tmp_path)
    issued = SQLiteTenantInvitationService(database).issue(
        tenant_id=tenant_id,
        created_by_user_id=owner_id,
        email="invitee@example.com",
        role=TenantRole.analyst,
        now=NOW,
    )
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    client = TestClient(_app(database))

    page = client.get("/accept-invitation", params={"token": issued.token})
    rejected_origin = client.post(
        "/accept-invitation",
        data={
            "token": issued.token,
            "display_name": "Invitee",
            "password": INVITEE_PASSWORD,
            "password_confirm": INVITEE_PASSWORD,
        },
        follow_redirects=False,
    )
    accepted = client.post(
        "/accept-invitation",
        headers={"Origin": ORIGIN},
        data={
            "token": issued.token,
            "display_name": "Invitee",
            "password": INVITEE_PASSWORD,
            "password_confirm": INVITEE_PASSWORD,
        },
        follow_redirects=False,
    )
    replay = client.get("/accept-invitation", params={"token": issued.token})

    assert page.status_code == 200
    assert "Join Customer One" in page.text
    assert "Create your Veridra account" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert rejected_origin.status_code == 403
    assert accepted.status_code == 303
    assert accepted.headers["location"] == "/agency"
    assert "veridra_session=" in accepted.headers["set-cookie"]
    assert issued.token not in accepted.text
    assert replay.status_code == 400
    assert SQLitePasswordAuthenticator(database).authenticate(
        email="invitee@example.com",
        tenant_slug="customer-one",
        password=INVITEE_PASSWORD,
    ) is not None


def test_existing_user_invitation_requires_login_and_accepts_matching_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, source_tenant_id, owner_id = _base(tmp_path)
    target_tenant_id = "2" * 24
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO tenants (id, slug, display_name, status, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (target_tenant_id, "customer-two", "Customer Two", "active", NOW.isoformat()),
        )
    issued = SQLiteExistingUserInvitationService(database).issue(
        tenant_id=target_tenant_id,
        created_by_user_id=owner_id,
        email="owner@example.com",
        role=TenantRole.analyst,
        now=NOW,
    )
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    app = _app(database)
    owner_identity = RequestIdentity(
        user_id=owner_id,
        tenant_id=source_tenant_id,
        membership_role=TenantRole.owner,
        session_id="existing-invite-session-1",
        authenticated_at=NOW,
    )

    @app.middleware("http")
    async def optional_identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.headers.get("x-authenticated") == "yes":
            bind_verified_request_identity(request, owner_identity)
        return await call_next(request)

    client = TestClient(app)
    anonymous = client.get(
        "/accept-invitation",
        params={"token": issued.token},
        follow_redirects=False,
    )
    parsed = urlsplit(anonymous.headers["location"])
    next_target = parse_qs(parsed.query)["next"][0]
    login_page = client.get(anonymous.headers["location"])
    accepted = client.post(
        "/accept-invitation",
        headers={"Origin": ORIGIN, "x-authenticated": "yes"},
        data={"token": issued.token},
        follow_redirects=False,
    )

    assert anonymous.status_code == 303
    assert parsed.path == "/login"
    assert next_target.startswith("/accept-invitation?token=")
    assert issued.token in next_target
    assert login_page.status_code == 200
    assert html_hidden_next(next_target) in login_page.text
    assert accepted.status_code == 303
    assert accepted.headers["location"] == "/agency"
    with sqlite3.connect(database) as connection:
        membership = connection.execute(
            "SELECT role, active FROM memberships WHERE tenant_id = ? AND user_id = ?",
            (target_tenant_id, owner_id),
        ).fetchone()
    assert membership == ("analyst", 1)


def html_hidden_next(next_target: str) -> str:
    import html

    return f"name='next' value='{html.escape(next_target, quote=True)}'"


def test_login_next_rejects_external_redirect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, _, _ = _base(tmp_path)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    client = TestClient(_app(database))

    response = client.post(
        "/login",
        headers={"Origin": ORIGIN},
        data={
            "tenant_slug": "customer-one",
            "email": "owner@example.com",
            "password": OWNER_PASSWORD,
            "next": "https://evil.example/steal",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/agency"
