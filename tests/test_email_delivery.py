from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

from veridra.core import demo_assessment
from veridra.email_delivery import (
    EmailAttemptStore,
    EmailEncryption,
    EmailStatus,
    SmtpConfig,
    send_lead_notification,
    send_monitoring_summary,
)
from veridra.lead_store import AuditLead

_LEAD_ID = "a" * 24
_PROJECT_ID = "b" * 24
_ASSESSMENT_ID = "c" * 24


def _config() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.example.test",
        port=587,
        encryption=EmailEncryption.starttls,
        sender_email="reports@example.com",
        sender_name="Example Agency",
        username="mailer@example.com",
        password_env="TEST_SMTP_PASSWORD",
    )


def _lead() -> AuditLead:
    return AuditLead(
        form_id="d" * 24,
        website="https://example.com/",
        name="Rafael <Admin>",
        email="rafael@example.com",
        company="Example & Co",
        consent_text="I agree.",
        consented_at=datetime(2026, 7, 23, 8, 0, tzinfo=UTC),
        assessment_id=_ASSESSMENT_ID,
    )


def test_smtp_config_reads_secret_only_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("TEST_SMTP_PASSWORD", "secret-value")
    config = _config()

    assert config.password() == "secret-value"
    assert "secret-value" not in str(config.model_dump(mode="json"))


def test_lead_notification_is_escaped_and_persisted(tmp_path: Path) -> None:
    observed: list[EmailMessage] = []

    def sender(config: SmtpConfig, message: EmailMessage) -> None:
        assert config.host == "smtp.example.test"
        observed.append(message)

    store = EmailAttemptStore(tmp_path)
    attempt = send_lead_notification(
        lead_id=_LEAD_ID,
        lead=_lead(),
        assessment=demo_assessment(),
        recipient="leads@example.com",
        config=_config(),
        store=store,
        sender=sender,
    )

    assert attempt is not None
    assert attempt.status == EmailStatus.delivered
    assert attempt.attempt_number == 1
    assert len(store.list_for_related(_LEAD_ID)) == 1
    raw = observed[0].as_string()
    assert "Rafael &lt;Admin&gt;" in raw
    assert "Example &amp; Co" in raw
    assert "Rafael <Admin>" in raw


def test_failed_delivery_is_recorded_without_raising(tmp_path: Path) -> None:
    def sender(config: SmtpConfig, message: EmailMessage) -> None:
        raise OSError("SMTP unavailable")

    attempt = send_monitoring_summary(
        project_id=_PROJECT_ID,
        project_name="Client site",
        target_url="https://example.com/",
        assessment_id=_ASSESSMENT_ID,
        assessment=demo_assessment(),
        recipient="client@example.com",
        config=_config(),
        store=EmailAttemptStore(tmp_path),
        sender=sender,
    )

    assert attempt is not None
    assert attempt.status == EmailStatus.failed
    assert "SMTP unavailable" in attempt.error


def test_attempt_numbers_increment_per_related_record(tmp_path: Path) -> None:
    store = EmailAttemptStore(tmp_path)

    def sender(config: SmtpConfig, message: EmailMessage) -> None:
        return None

    first = send_monitoring_summary(
        project_id=_PROJECT_ID,
        project_name="Client site",
        target_url="https://example.com/",
        assessment_id=_ASSESSMENT_ID,
        assessment=demo_assessment(),
        recipient="client@example.com",
        config=_config(),
        store=store,
        sender=sender,
    )
    second = send_monitoring_summary(
        project_id=_PROJECT_ID,
        project_name="Client site",
        target_url="https://example.com/",
        assessment_id=_ASSESSMENT_ID,
        assessment=demo_assessment(),
        recipient="client@example.com",
        config=_config(),
        store=store,
        sender=sender,
    )

    assert first is not None and first.attempt_number == 1
    assert second is not None and second.attempt_number == 2


def test_missing_environment_configuration_disables_delivery(monkeypatch) -> None:
    for name in (
        "VERIDRA_SMTP_HOST",
        "VERIDRA_SMTP_SENDER",
        "VERIDRA_SMTP_PORT",
        "VERIDRA_SMTP_ENCRYPTION",
    ):
        monkeypatch.delenv(name, raising=False)

    assert send_lead_notification(
        lead_id=_LEAD_ID,
        lead=_lead(),
        assessment=demo_assessment(),
        recipient="leads@example.com",
    ) is None
