from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from veridra.email_delivery import EmailEncryption, EmailStatus, SmtpConfig
from veridra.identity_email_delivery import IdentityEmailAttemptStore, PasswordResetEmailAdapter
from veridra.password_recovery_api import PasswordResetDelivery

TOKEN = "reset-token-that-must-never-be-persisted"
NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def _config() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.example.test",
        port=587,
        encryption=EmailEncryption.starttls,
        sender_email="security@example.com",
        sender_name="Veridra Security",
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

    adapter(
        PasswordResetDelivery(
            email="owner@example.com",
            token=TOKEN,
            expires_at=NOW + timedelta(minutes=30),
        )
    )

    assert len(messages) == 1
    assert TOKEN in messages[0].get_content()
    attempts = store.list()
    assert len(attempts) == 1
    assert attempts[0][1].status is EmailStatus.delivered
    assert attempts[0][1].recipient == "owner@example.com"
    assert TOKEN not in attempts[0][0]
    assert TOKEN.encode("utf-8") not in next(tmp_path.glob("*.json")).read_bytes()


def test_password_reset_smtp_failure_is_persisted_without_raising(tmp_path: Path) -> None:
    store = IdentityEmailAttemptStore(tmp_path)

    def fail(config: SmtpConfig, message: EmailMessage) -> None:
        raise OSError("smtp unavailable")

    adapter = PasswordResetEmailAdapter(config=_config(), store=store, sender=fail)
    adapter(
        PasswordResetDelivery(
            email="owner@example.com",
            token=TOKEN,
            expires_at=NOW + timedelta(minutes=30),
        )
    )

    attempts = store.list()
    assert len(attempts) == 1
    assert attempts[0][1].status is EmailStatus.failed
    assert attempts[0][1].error == "smtp unavailable"
