from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_middleware import VerifiedIdentityMiddleware
from veridra.identity_tenancy import TenantRole
from veridra.invitation_api import router as invitation_router
from veridra.password_auth import SQLitePasswordAuthenticator
from veridra.session_cookie import SecureSessionCookieExtractor
from veridra.session_identity_adapter import ServerSideSessionIdentityAdapter
from veridra.session_lifecycle import SessionLifecycleService
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.tenant_invitations import SQLiteTenantInvitationService, TenantInvitationError

NOW = datetime(2026, 7, 25, 10, 0, tzinfo=UTC)
OWNER_PASSWORD = "owner-correct-horse-battery"
INVITED_PASSWORD = "invited-correct-horse-battery"


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "identity.sqlite3"
    SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password=OWNER_PASSWORD,
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    return database


def _owner_client(database: Path) -> TestClient:
    store = SQLiteIdentityRecordStore(database)
    records = SQLitePasswordAuthenticator(database).authenticate(
        email="owner@example.com",
        tenant_slug="customer-one",
        password=OWNER_PASSWORD,
    )
    assert records is not None
    issued = SessionLifecycleService(store, clock=lambda: NOW).issue(
        user_id=records.user.id,
        tenant_id=records.tenant.id,
        lifetime=timedelta(hours=1),
    )
    app = FastAPI()
    app.state.veridra_identity_store = store
    app.add_middleware(
        VerifiedIdentityMiddleware,
        adapter=ServerSideSessionIdentityAdapter(
            extractor=SecureSessionCookieExtractor(),
            store=store,
            clock=lambda: NOW + timedelta(minutes=1),
        ),
    )
    app.include_router(invitation_router)
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set("veridra_session", issued.credential)
    return client


def test_owner_invites_new_user_and_token_is_one_time(tmp_path: Path) -> None:
    database = _database(tmp_path)
    client = _owner_client(database)

    created = client.post(
        "/api/invitations",
        json={"email": "analyst@example.com", "role": "analyst"},
    )
    assert created.status_code == 201
    token = created.json()["token"]
    assert token not in database.read_bytes().decode("utf-8", errors="ignore")

    accepted = client.post(
        "/api/invitations/accept",
        json={
            "token": token,
            "display_name": "Invited analyst",
            "password": INVITED_PASSWORD,
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "analyst"

    records = SQLitePasswordAuthenticator(database).authenticate(
        email="analyst@example.com",
        tenant_slug="customer-one",
        password=INVITED_PASSWORD,
    )
    assert records is not None
    assert records.membership.role is TenantRole.analyst

    replay = client.post(
        "/api/invitations/accept",
        json={
            "token": token,
            "display_name": "Duplicate",
            "password": INVITED_PASSWORD,
        },
    )
    assert replay.status_code == 400


def test_invitation_rejects_owner_role_existing_user_and_expiry(tmp_path: Path) -> None:
    database = _database(tmp_path)
    service = SQLiteTenantInvitationService(database)
    authenticator = SQLitePasswordAuthenticator(database)
    owner = authenticator.authenticate(
        email="owner@example.com",
        tenant_slug="customer-one",
        password=OWNER_PASSWORD,
    )
    assert owner is not None

    with pytest.raises(TenantInvitationError, match="Owner invitations"):
        service.issue(
            tenant_id=owner.tenant.id,
            created_by_user_id=owner.user.id,
            email="new@example.com",
            role=TenantRole.owner,
            now=NOW,
        )
    with pytest.raises(TenantInvitationError, match="Existing users"):
        service.issue(
            tenant_id=owner.tenant.id,
            created_by_user_id=owner.user.id,
            email="owner@example.com",
            role=TenantRole.viewer,
            now=NOW,
        )

    issued = service.issue(
        tenant_id=owner.tenant.id,
        created_by_user_id=owner.user.id,
        email="expired@example.com",
        role=TenantRole.viewer,
        now=NOW,
        lifetime=timedelta(minutes=1),
    )
    with pytest.raises(TenantInvitationError, match="expired"):
        service.accept(
            token=issued.token,
            display_name="Expired",
            password=INVITED_PASSWORD,
            now=NOW + timedelta(minutes=2),
        )


def test_owner_lists_and_cancels_active_invitation(tmp_path: Path) -> None:
    client = _owner_client(_database(tmp_path))
    created = client.post(
        "/api/invitations",
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    assert created.status_code == 201
    token = created.json()["token"]

    listed = client.get("/api/invitations")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    invitation_id = listed.json()[0]["id"]
    assert "token" not in listed.json()[0]

    cancelled = client.delete(f"/api/invitations/{invitation_id}")
    assert cancelled.status_code == 204
    assert client.get("/api/invitations").json() == []

    rejected = client.post(
        "/api/invitations/accept",
        json={
            "token": token,
            "display_name": "Cancelled",
            "password": INVITED_PASSWORD,
        },
    )
    assert rejected.status_code == 400
    assert client.delete("/api/invitations/0" * 12).status_code == 404


def test_resend_atomically_replaces_invitation_token(tmp_path: Path) -> None:
    client = _owner_client(_database(tmp_path))
    created = client.post(
        "/api/invitations",
        json={"email": "sales@example.com", "role": "sales"},
    )
    assert created.status_code == 201
    old_token = created.json()["token"]
    invitation_id = client.get("/api/invitations").json()[0]["id"]

    resent = client.post(f"/api/invitations/{invitation_id}/resend")
    assert resent.status_code == 200
    new_token = resent.json()["token"]
    assert new_token != old_token
    active = client.get("/api/invitations").json()
    assert len(active) == 1
    assert active[0]["id"] != invitation_id

    old_rejected = client.post(
        "/api/invitations/accept",
        json={
            "token": old_token,
            "display_name": "Old token",
            "password": INVITED_PASSWORD,
        },
    )
    assert old_rejected.status_code == 400

    accepted = client.post(
        "/api/invitations/accept",
        json={
            "token": new_token,
            "display_name": "Sales user",
            "password": INVITED_PASSWORD,
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "sales"
