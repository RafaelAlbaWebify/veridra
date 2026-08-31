from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from veridra.email_delivery import EmailStatus, SmtpConfig
from veridra.report_delivery import ReportDeliveryStore, send_report_pdf


def _config() -> SmtpConfig:
    return SmtpConfig(
        host="mail.test",
        port=587,
        sender_email="reports@example.com",
        sender_name="Agency",
    )


def test_report_delivery_records_attachment_and_success(tmp_path: Path) -> None:
    messages: list[EmailMessage] = []
    store = ReportDeliveryStore(tmp_path)

    attempt = send_report_pdf(
        project_id="a" * 24,
        assessment_id="b" * 24,
        recipient="client@example.com",
        subject="Your report",
        message_text="Attached.",
        pdf_content=b"%PDF-test",
        filename="assessment.pdf",
        store=store,
        config=_config(),
        sender=lambda _config, message: messages.append(message),
    )

    assert attempt is not None
    assert attempt.status == EmailStatus.delivered
    assert attempt.attempt_number == 1
    attachment = next(messages[0].iter_attachments())
    assert attachment.get_filename() == "assessment.pdf"
    assert attachment.get_content_type() == "application/pdf"
    assert store.list_for_project("a" * 24)[0][1] == attempt


def test_report_delivery_records_failure_and_retry(tmp_path: Path) -> None:
    store = ReportDeliveryStore(tmp_path)

    def fail(_config: SmtpConfig, _message: EmailMessage) -> None:
        raise OSError("delivery unavailable")

    first = send_report_pdf(
        project_id="a" * 24,
        assessment_id="b" * 24,
        recipient="client@example.com",
        subject="Your report",
        message_text="Attached.",
        pdf_content=b"%PDF-test",
        filename="assessment.pdf",
        store=store,
        config=_config(),
        sender=fail,
    )
    second = send_report_pdf(
        project_id="a" * 24,
        assessment_id="b" * 24,
        recipient="client@example.com",
        subject="Your report",
        message_text="Attached.",
        pdf_content=b"%PDF-test",
        filename="assessment.pdf",
        store=store,
        config=_config(),
        sender=lambda _config, _message: None,
    )

    assert first is not None and first.status == EmailStatus.failed
    assert second is not None and second.status == EmailStatus.delivered
    assert second.attempt_number == 2
    assert len(store.list_for_project("a" * 24)) == 2


def test_report_delivery_returns_none_without_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VERIDRA_SMTP_HOST", raising=False)
    monkeypatch.delenv("VERIDRA_SMTP_SENDER", raising=False)

    attempt = send_report_pdf(
        project_id="a" * 24,
        assessment_id="b" * 24,
        recipient="client@example.com",
        subject="Your report",
        message_text="Attached.",
        pdf_content=b"%PDF-test",
        filename="assessment.pdf",
        store=ReportDeliveryStore(tmp_path),
    )

    assert attempt is None
    assert list(tmp_path.glob("*.json")) == []


def test_report_delivery_can_capture_email_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = tmp_path / "captured-mail"
    monkeypatch.setenv("VERIDRA_REPORT_EMAIL_CAPTURE_DIR", str(capture.resolve()))

    attempt = send_report_pdf(
        project_id="a" * 24,
        assessment_id="b" * 24,
        recipient="acceptance@example.test",
        subject="Acceptance report",
        message_text="Captured locally.",
        pdf_content=b"%PDF-captured",
        filename="acceptance.pdf",
        store=ReportDeliveryStore(tmp_path / "attempts"),
        config=_config(),
    )

    messages = list(capture.glob("report-*.eml"))
    assert attempt is not None and attempt.status is EmailStatus.delivered
    assert len(messages) == 1
    content = messages[0].read_bytes()
    assert b"Acceptance report" in content
    assert b"application/pdf" in content
    assert b"acceptance.pdf" in content
