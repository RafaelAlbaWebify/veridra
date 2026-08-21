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
from veridra.identity_email_delivery import IdentityEmailAttemptStore, TenantSignupEmailAdapter
from veridra.runtime_config import RuntimeConfig, RuntimeEnvironment
from veridra.runtime_legal import LegalLinks
from veridra.signup_legal_evidence import SQLiteSignupLegalEvidenceStore
from veridra.signup_web import router
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore

ORIGIN = "https://app.example.com"
PASSWORD = "signup-correct-horse-battery"
TERMS = "https://legal.example.com/terms-v1"
PRIVACY = "https://legal.example.com/privacy-v1"


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


def _client(tmp_path: Path) -> tuple[TestClient, Path, list[EmailMessage], Path]:
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
    email_evidence = tmp_path / "email-evidence"
    app = FastAPI()
    app.state.veridra_runtime_config = _runtime(identity, tenants)
    app.state.veridra_identity_database = identity
    app.state.veridra_identity_store = SQLiteIdentityRecordStore(identity)
    app.state.veridra_tenant_data_root = tenants
    app.state.veridra_legal_links = LegalLinks(privacy_url=PRIVACY, terms_url=TERMS)
    app.state.veridra_tenant_signup_delivery = TenantSignupEmailAdapter(
        config=_smtp(),
        store=IdentityEmailAttemptStore(email_evidence),
        signup_origin=ORIGIN,
        sender=lambda config, message: messages.append(message),
    )
    app.include_router(router)
    return TestClient(app, base_url=ORIGIN), identity, messages, email_evidence


def _form(*, accepted: bool) -> dict[str, str]:
    data = {
        "tenant_name": "Second agency",
        "tenant_slug": "second-agency",
        "owner_name": "Second Owner",
        "owner_email": "second@example.com",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
    }
    if accepted:
        data["terms_accepted"] = "yes"
    return data


def _token(message: EmailMessage) -> str:
    match = re.search(r"/verify-signup\?token=([^\s]+)", message.get_content())
    assert match is not None
    return unquote(match.group(1))


def _count(database: Path, table: str) -> int:
    with sqlite3.connect(database) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_signup_displays_privacy_and_requires_terms(tmp_path: Path) -> None:
    client, identity, messages, _ = _client(tmp_path)

    page = client.get("/signup")
    refused = client.post(
        "/signup",
        data=_form(accepted=False),
        headers={"origin": ORIGIN},
    )

    assert page.status_code == 200
    assert TERMS in page.text
    assert PRIVACY in page.text
    assert "terms_accepted" in page.text
    assert refused.status_code == 400
    assert "must agree to the Terms of Service" in refused.text
    assert messages == []
    assert SQLiteSignupLegalEvidenceStore(identity).latest_for_email(
        "second@example.com"
    ) is None


def test_accepted_terms_are_persisted_and_linked_after_activation(tmp_path: Path) -> None:
    client, identity, messages, _ = _client(tmp_path)

    requested = client.post(
        "/signup",
        data=_form(accepted=True),
        headers={"origin": ORIGIN},
    )

    assert requested.status_code == 202
    assert len(messages) == 1
    token = _token(messages[0])
    evidence = SQLiteSignupLegalEvidenceStore(identity).latest_for_email(
        "second@example.com"
    )
    assert evidence is not None
    assert evidence.terms_url == TERMS
    assert evidence.privacy_url == PRIVACY
    assert evidence.owner_name == "Second Owner"
    assert evidence.activated_at is None
    assert token not in evidence.token_hash

    completed = client.post(
        "/verify-signup",
        data={"token": token},
        headers={"origin": ORIGIN},
        follow_redirects=False,
    )

    assert completed.status_code == 303
    activated = SQLiteSignupLegalEvidenceStore(identity).latest_for_email(
        "second@example.com"
    )
    assert activated is not None
    assert activated.activated_at is not None
    assert activated.tenant_id is not None
    assert activated.user_id is not None


def test_smtp_failure_removes_pending_signup_and_legal_evidence(tmp_path: Path) -> None:
    client, identity, _, email_evidence = _client(tmp_path)

    def fail(config: SmtpConfig, message: EmailMessage) -> None:
        raise OSError("smtp unavailable")

    app = cast(FastAPI, client.app)
    app.state.veridra_tenant_signup_delivery = TenantSignupEmailAdapter(
        config=_smtp(),
        store=IdentityEmailAttemptStore(email_evidence),
        signup_origin=ORIGIN,
        sender=fail,
    )

    response = client.post(
        "/signup",
        data=_form(accepted=True),
        headers={"origin": ORIGIN},
    )

    assert response.status_code == 503
    assert _count(identity, "tenant_signup_requests") == 0
    assert SQLiteSignupLegalEvidenceStore(identity).latest_for_email(
        "second@example.com"
    ) is None
