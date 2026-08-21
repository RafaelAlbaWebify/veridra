from __future__ import annotations

import re
import sqlite3
from email.message import EmailMessage
from pathlib import Path
from typing import cast
from urllib.parse import unquote

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.email_delivery import EmailEncryption, SmtpConfig
from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_email_delivery import (
    IdentityEmailAttemptStore,
    IdentityEmailKind,
    TenantSignupEmailAdapter,
)
from veridra.identity_tenancy import Tenant
from veridra.runtime_config import RuntimeConfig, RuntimeEnvironment
from veridra.runtime_legal import LegalLinks
from veridra.signup_web import router
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.workspace_policy import PlanName, WorkspaceStore

ORIGIN = "https://app.example.com"
PASSWORD = "signup-correct-horse-battery"


def _runtime(identity: Path, tenants: Path) -> RuntimeConfig:
    return RuntimeConfig(
        environment=RuntimeEnvironment.test,
        identity_database=identity,
        tenant_data_root=tenants,
        trusted_origin=ORIGIN,
        allowed_hosts=("app.example.com",),
        trusted_proxy_ips=(),
        max_request_body_bytes=1_000_000,
        bind_host="127.0.0.1",
        bind_port=8000,
    )


def _smtp() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.example.test",
        port=587,
        encryption=EmailEncryption.starttls,
        sender_email="security@example.com",
        sender_name="Veridra",
    )


def _client(tmp_path: Path) -> tuple[TestClient, Path, Path, list[EmailMessage], Path]:
    identity = tmp_path / "identity" / "identity.sqlite3"
    tenants = tmp_path / "tenants"
    SQLiteIdentityBootstrap(identity, tenant_data_root=tenants).create_first_owner(
        tenant_slug="first-agency",
        tenant_name="First agency",
        owner_email="first@example.com",
        owner_name="First Owner",
        password="first-owner-password-123",
        confirmation=BOOTSTRAP_CONFIRMATION,
    )
    messages: list[EmailMessage] = []
    evidence = tmp_path / "identity" / "identity-email-deliveries"
    delivery = TenantSignupEmailAdapter(
        config=_smtp(),
        store=IdentityEmailAttemptStore(evidence),
        signup_origin=ORIGIN,
        sender=lambda config, message: messages.append(message),
    )
    app = FastAPI()
    app.state.veridra_runtime_config = _runtime(identity, tenants)
    app.state.veridra_identity_database = identity
    app.state.veridra_identity_store = SQLiteIdentityRecordStore(identity)
    app.state.veridra_tenant_data_root = tenants
    app.state.veridra_tenant_signup_delivery = delivery
    app.include_router(router)
    return TestClient(app, base_url=ORIGIN), identity, tenants, messages, evidence


def _count(database: Path, table: str) -> int:
    with sqlite3.connect(database) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _token(message: EmailMessage) -> str:
    match = re.search(r"/verify-signup\?token=([^\s]+)", message.get_content())
    assert match is not None
    return unquote(match.group(1))


def _form(*, slug: str = "second-agency", email: str = "second@example.com") -> dict[str, str]:
    return {
        "tenant_name": "Second agency",
        "tenant_slug": slug,
        "owner_name": "Second Owner",
        "owner_email": email,
        "password": PASSWORD,
        "password_confirm": PASSWORD,
    }


def test_second_agency_can_signup_only_after_email_confirmation(tmp_path: Path) -> None:
    client, identity, tenants, messages, evidence = _client(tmp_path)

    assert client.get("/signup").status_code == 200
    missing_origin = client.post("/signup", data=_form())
    assert missing_origin.status_code == 403

    requested = client.post("/signup", data=_form(), headers={"origin": ORIGIN})

    assert requested.status_code == 202
    assert "Check your email" in requested.text
    assert len(messages) == 1
    assert _count(identity, "tenants") == 1
    assert _count(identity, "users") == 1
    token = _token(messages[0])
    evidence_files = list(evidence.glob("*.json"))
    assert len(evidence_files) == 1
    assert token.encode("utf-8") not in evidence_files[0].read_bytes()
    attempts = IdentityEmailAttemptStore(evidence).list()
    assert attempts[0][1].kind is IdentityEmailKind.tenant_signup_verification

    preview = client.get(f"/verify-signup?token={token}")

    assert preview.status_code == 200
    assert "Create my workspace" in preview.text
    assert _count(identity, "tenants") == 1
    assert _count(identity, "users") == 1

    completed = client.post(
        "/verify-signup",
        data={"token": token},
        headers={"origin": ORIGIN},
        follow_redirects=False,
    )

    assert completed.status_code == 303
    assert completed.headers["location"] == "/agency"
    assert "set-cookie" in completed.headers
    assert _count(identity, "tenants") == 2
    assert _count(identity, "users") == 2
    assert _count(identity, "memberships") == 2
    with sqlite3.connect(identity) as connection:
        row = connection.execute(
            "SELECT id, email_verified_at, status FROM users WHERE email = ?",
            ("second@example.com",),
        ).fetchone()
        tenant = connection.execute(
            "SELECT id FROM tenants WHERE slug = ?",
            ("second-agency",),
        ).fetchone()
    assert row is not None
    assert row[1] is not None
    assert row[2] == "active"
    assert tenant is not None
    workspace = WorkspaceStore(tenants / str(tenant[0]) / "workspace").load()
    assert workspace.plan is PlanName.free
    assert _count(identity, "tenant_signup_requests") == 0
    assert client.get(f"/verify-signup?token={token}").status_code == 400


def test_legal_signup_fails_closed_when_evidence_disappears(tmp_path: Path) -> None:
    client, identity, _, messages, _ = _client(tmp_path)
    app = cast(FastAPI, client.app)
    app.state.veridra_legal_links = LegalLinks(
        privacy_url="https://legal.example.com/privacy-v1",
        terms_url="https://legal.example.com/terms-v1",
    )
    form = _form()
    form["terms_accepted"] = "yes"

    requested = client.post("/signup", data=form, headers={"origin": ORIGIN})
    assert requested.status_code == 202
    token = _token(messages[-1])
    with sqlite3.connect(identity) as connection:
        connection.execute("DELETE FROM signup_legal_acceptances")

    completed = client.post(
        "/verify-signup",
        data={"token": token},
        headers={"origin": ORIGIN},
        follow_redirects=False,
    )

    assert completed.status_code == 400
    assert _count(identity, "tenants") == 1
    assert _count(identity, "users") == 1
    assert _count(identity, "tenant_signup_requests") == 1


def test_signup_rejects_nonempty_orphan_tenant_state_without_deleting_it(
    tmp_path: Path,
) -> None:
    client, identity, tenants, messages, _ = _client(tmp_path)
    requested = client.post("/signup", data=_form(), headers={"origin": ORIGIN})
    assert requested.status_code == 202
    token = _token(messages[-1])
    tenant_id = Tenant.build(
        slug="second-agency",
        display_name="Second agency",
    ).id
    marker = tenants / tenant_id / "projects" / "orphan.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("preserve", encoding="utf-8")

    completed = client.post(
        "/verify-signup",
        data={"token": token},
        headers={"origin": ORIGIN},
        follow_redirects=False,
    )

    assert completed.status_code == 400
    assert _count(identity, "tenants") == 1
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert not (tenants / tenant_id / "workspace" / "workspace.json").exists()


def test_existing_email_is_non_enumerating_and_sends_no_verification(tmp_path: Path) -> None:
    client, identity, _, messages, _ = _client(tmp_path)

    response = client.post(
        "/signup",
        data=_form(slug="another-agency", email="first@example.com"),
        headers={"origin": ORIGIN},
    )

    assert response.status_code == 202
    assert "Check your email" in response.text
    assert messages == []
    assert _count(identity, "tenants") == 1
    assert _count(identity, "tenant_signup_requests") == 0


def test_existing_workspace_slug_is_reported_without_sending_email(tmp_path: Path) -> None:
    client, identity, _, messages, _ = _client(tmp_path)

    response = client.post(
        "/signup",
        data=_form(slug="first-agency", email="different@example.com"),
        headers={"origin": ORIGIN},
    )

    assert response.status_code == 409
    assert "Workspace slug unavailable" in response.text
    assert messages == []
    assert _count(identity, "tenants") == 1


def test_smtp_failure_discards_pending_signup_secret(tmp_path: Path) -> None:
    client, identity, _, _, evidence = _client(tmp_path)

    def fail(config: SmtpConfig, message: EmailMessage) -> None:
        raise OSError("smtp unavailable")

    app = cast(FastAPI, client.app)
    app.state.veridra_tenant_signup_delivery = TenantSignupEmailAdapter(
        config=_smtp(),
        store=IdentityEmailAttemptStore(evidence),
        signup_origin=ORIGIN,
        sender=fail,
    )

    response = client.post("/signup", data=_form(), headers={"origin": ORIGIN})

    assert response.status_code == 503
    assert _count(identity, "tenant_signup_requests") == 0
    attempts = IdentityEmailAttemptStore(evidence).list()
    assert len(attempts) == 1
    assert attempts[0][1].kind is IdentityEmailKind.tenant_signup_verification
