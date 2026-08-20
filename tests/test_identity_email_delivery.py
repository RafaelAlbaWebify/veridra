from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pytest

from veridra.email_delivery import EmailEncryption, EmailStatus, SmtpConfig
from veridra.identity_email_delivery import (
    IdentityEmailAttemptStore,
    IdentityEmailKind,
    PasswordResetEmailAdapter,
    TenantInvitationDelivery,
    TenantInvitationEmailAdapter,
)
from veridra.password_recovery_api import PasswordResetDelivery

TOKEN = "reset-token-that-must-never-be-persisted"
INVITATION_TOKEN = "invitation-token-that-must-never-be-persisted-123456"
NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def _config() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.example.test",
        port=587,
        encryption=EmailEncryption.starttls,
        sender_email="security@example.com",
        sender_name="Veridra Security",
    )


def _delivery() -> PasswordResetDelivery:
    return PasswordResetDelivery(
        email="owner@example.com",
        token=TOKEN,
        expires_at=NOW + timedelta(minutes=30),
    )


def test_password_reset_email_sends_token_but_evidence_keeps_only_hash(
    tmp_path: Path,
) -> None:
    messages: list[EmailMessage] = []
    store = IdentityEmailAttemptStore(tmp_path)
    adapter = PasswordResetEmailAdapter(
        config=_config(),
        store=store,
        sender=lambda config, message: messages.append(message),
    )

    adapter(_delivery())

    assert len(messages) == 1
    assert TOKEN in messages[0].get_content()
    attempts = store.list()
    assert len(attempts) == 1
    assert attempts[0][1].status is EmailStatus.delivered
    assert attempts[0][1].recipient == "owner@example.com"
    assert TOKEN not in attempts[0][0]
    assert TOKEN.encode("utf-8") not in next(tmp_path.glob("*.json")).read_bytes()


def test_password_reset_email_uses_browser_reset_link_when_origin_is_configured(
    tmp_path: Path,
) -> None:
    messages: list[EmailMessage] = []
    store = IdentityEmailAttemptStore(tmp_path)
    adapter = PasswordResetEmailAdapter(
        config=_config(),
        store=store,
        reset_origin="https://app.example.com/",
        sender=lambda config, message: messages.append(message),
    )

    adapter(_delivery())

    body = messages[0].get_content()
    assert f"https://app.example.com/reset-password?token={TOKEN}" in body
    assert "/api/auth/password-recovery/reset" not in body
    assert TOKEN.encode("utf-8") not in next(tmp_path.glob("*.json")).read_bytes()


def test_invitation_email_uses_browser_acceptance_link_and_hash_only_evidence(
    tmp_path: Path,
) -> None:
    messages: list[EmailMessage] = []
    store = IdentityEmailAttemptStore(tmp_path)
    adapter = TenantInvitationEmailAdapter(
        config=_config(),
        store=store,
        invitation_origin="https://app.example.com/",
        sender=lambda config, message: messages.append(message),
    )
    delivery = TenantInvitationDelivery(
        email="invitee@example.com",
        token=INVITATION_TOKEN,
        expires_at=NOW + timedelta(hours=48),
    )

    delivered = adapter(delivery)

    assert delivered
    assert len(messages) == 1
    assert (
        f"https://app.example.com/accept-invitation?token={INVITATION_TOKEN}"
        in messages[0].get_content()
    )
    attempts = store.list()
    assert len(attempts) == 1
    assert attempts[0][1].kind is IdentityEmailKind.tenant_invitation
    assert attempts[0][1].status is EmailStatus.delivered
    assert attempts[0][1].recipient == "invitee@example.com"
    assert INVITATION_TOKEN.encode("utf-8") not in next(tmp_path.glob("*.json")).read_bytes()


def test_invitation_email_failure_returns_false_and_records_failure(tmp_path: Path) -> None:
    store = IdentityEmailAttemptStore(tmp_path)

    def fail(config: SmtpConfig, message: EmailMessage) -> None:
        raise OSError("smtp unavailable")

    adapter = TenantInvitationEmailAdapter(
        config=_config(),
        store=store,
        invitation_origin="https://app.example.com",
        sender=fail,
    )

    delivered = adapter(
        TenantInvitationDelivery(
            email="invitee@example.com",
            token=INVITATION_TOKEN,
            expires_at=NOW + timedelta(hours=48),
        )
    )

    assert not delivered
    attempts = store.list()
    assert len(attempts) == 1
    assert attempts[0][1].status is EmailStatus.failed
    assert attempts[0][1].error == "smtp unavailable"


def test_password_reset_smtp_failure_is_persisted_without_raising(tmp_path: Path) -> None:
    store = IdentityEmailAttemptStore(tmp_path)

    def fail(config: SmtpConfig, message: EmailMessage) -> None:
        raise OSError("smtp unavailable")

    adapter = PasswordResetEmailAdapter(config=_config(), store=store, sender=fail)
    adapter(_delivery())

    attempts = store.list()
    assert len(attempts) == 1
    assert attempts[0][1].status is EmailStatus.failed
    assert attempts[0][1].error == "smtp unavailable"


def test_password_reset_evidence_failure_does_not_escape_delivery_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[EmailMessage] = []
    store = IdentityEmailAttemptStore(tmp_path)

    def fail_save(attempt: object) -> str:
        raise OSError("evidence unavailable")

    monkeypatch.setattr(store, "save", fail_save)
    adapter = PasswordResetEmailAdapter(
        config=_config(),
        store=store,
        sender=lambda config, message: messages.append(message),
    )

    adapter(_delivery())

    assert len(messages) == 1
    assert store.list() == []
