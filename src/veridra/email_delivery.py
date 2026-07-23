from __future__ import annotations

import hashlib
import html
import json
import os
import smtplib
import ssl
from collections.abc import Callable
from datetime import UTC, datetime
from email.message import EmailMessage
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from .core import Assessment
from .lead_store import AuditLead

_MAX_MESSAGE_BYTES = 256_000
_SMTP_TIMEOUT_SECONDS = 10.0


class EmailDeliveryError(RuntimeError):
    pass


class EmailEncryption(StrEnum):
    starttls = "starttls"
    implicit_tls = "implicit_tls"


class EmailStatus(StrEnum):
    delivered = "delivered"
    failed = "failed"


class EmailKind(StrEnum):
    lead_notification = "lead_notification"
    monitoring_summary = "monitoring_summary"


class SmtpConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    encryption: EmailEncryption = EmailEncryption.starttls
    sender_email: EmailStr
    sender_name: str = Field(default="Veridra", min_length=1, max_length=120)
    username: str | None = Field(default=None, max_length=320)
    password_env: str = Field(default="VERIDRA_SMTP_PASSWORD", pattern=r"^[A-Z0-9_]{1,80}$")

    @model_validator(mode="after")
    def validate_port(self) -> SmtpConfig:
        if self.encryption == EmailEncryption.implicit_tls and self.port == 25:
            raise ValueError("Implicit TLS cannot use the clear-text SMTP port 25.")
        return self

    @classmethod
    def from_environment(cls) -> SmtpConfig | None:
        host = os.environ.get("VERIDRA_SMTP_HOST", "").strip()
        sender = os.environ.get("VERIDRA_SMTP_SENDER", "").strip()
        if not host and not sender:
            return None
        if not host or not sender:
            raise EmailDeliveryError(
                "Both VERIDRA_SMTP_HOST and VERIDRA_SMTP_SENDER are required."
            )
        try:
            return cls(
                host=host,
                port=int(os.environ.get("VERIDRA_SMTP_PORT", "587")),
                encryption=EmailEncryption(
                    os.environ.get("VERIDRA_SMTP_ENCRYPTION", "starttls")
                ),
                sender_email=sender,
                sender_name=os.environ.get("VERIDRA_SMTP_SENDER_NAME", "Veridra"),
                username=os.environ.get("VERIDRA_SMTP_USERNAME") or None,
                password_env=os.environ.get(
                    "VERIDRA_SMTP_PASSWORD_ENV", "VERIDRA_SMTP_PASSWORD"
                ),
            )
        except (TypeError, ValueError) as exc:
            raise EmailDeliveryError("Invalid SMTP environment configuration.") from exc

    def password(self) -> str | None:
        value = os.environ.get(self.password_env)
        return value if value else None


class EmailAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EmailKind
    recipient: EmailStr
    attempted_at: datetime
    status: EmailStatus
    subject: str = Field(min_length=1, max_length=200)
    message_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_number: int = Field(ge=1)
    related_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    assessment_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    error: str = Field(default="", max_length=1000)


def default_email_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    root = Path(configured).expanduser().resolve() if configured else Path.home() / ".veridra"
    return root / "email-deliveries"


def _canonical_bytes(model: BaseModel) -> bytes:
    return json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class EmailAttemptStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_email_directory()

    def _path(self, identifier: str) -> Path:
        if len(identifier) != 24 or any(char not in "0123456789abcdef" for char in identifier):
            raise EmailDeliveryError("Invalid email-attempt identifier.")
        return self.directory / f"{identifier}.json"

    def save(self, attempt: EmailAttempt) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        content = _canonical_bytes(attempt)
        identifier = hashlib.sha256(content).hexdigest()[:24]
        destination = self._path(identifier)
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{identifier}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return identifier

    def list_for_related(self, related_id: str) -> list[tuple[str, EmailAttempt]]:
        self._path(related_id)
        if not self.directory.exists():
            return []
        attempts: list[tuple[str, EmailAttempt]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                attempt = EmailAttempt.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if attempt.related_id == related_id:
                attempts.append((path.stem, attempt))
        return sorted(
            attempts,
            key=lambda item: (item[1].attempted_at, item[1].attempt_number, item[0]),
            reverse=True,
        )


SmtpSender = Callable[[SmtpConfig, EmailMessage], None]


def _default_sender(config: SmtpConfig, message: EmailMessage) -> None:
    context = ssl.create_default_context()
    password = config.password()
    if config.encryption == EmailEncryption.implicit_tls:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            config.host,
            config.port,
            timeout=_SMTP_TIMEOUT_SECONDS,
            context=context,
        )
    else:
        client = smtplib.SMTP(config.host, config.port, timeout=_SMTP_TIMEOUT_SECONDS)
    with client:
        client.ehlo()
        if config.encryption == EmailEncryption.starttls:
            client.starttls(context=context)
            client.ehlo()
        if config.username:
            if password is None:
                raise EmailDeliveryError(
                    f"SMTP password environment variable {config.password_env} is not set."
                )
            client.login(config.username, password)
        client.send_message(message)


def _attempt_number(store: EmailAttemptStore, related_id: str) -> int:
    return len(store.list_for_related(related_id)) + 1


def _send(
    *,
    kind: EmailKind,
    related_id: str,
    assessment_id: str | None,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
    config: SmtpConfig | None = None,
    store: EmailAttemptStore | None = None,
    sender: SmtpSender = _default_sender,
) -> EmailAttempt | None:
    active = config if config is not None else SmtpConfig.from_environment()
    if active is None:
        return None
    message = EmailMessage()
    message["From"] = f"{active.sender_name} <{active.sender_email}>"
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    raw = message.as_bytes()
    if len(raw) > _MAX_MESSAGE_BYTES:
        raise EmailDeliveryError("Generated email exceeds the 256 KB delivery limit.")
    digest = hashlib.sha256(raw).hexdigest()
    active_store = store or EmailAttemptStore()
    status = EmailStatus.delivered
    error = ""
    try:
        sender(active, message)
    except (OSError, smtplib.SMTPException, EmailDeliveryError, ValueError) as exc:
        status = EmailStatus.failed
        error = str(exc)[:1000]
    attempt = EmailAttempt(
        kind=kind,
        recipient=recipient,
        attempted_at=datetime.now(UTC),
        status=status,
        subject=subject,
        message_sha256=digest,
        attempt_number=_attempt_number(active_store, related_id),
        related_id=related_id,
        assessment_id=assessment_id,
        error=error,
    )
    active_store.save(attempt)
    return attempt


def send_lead_notification(
    *,
    lead_id: str,
    lead: AuditLead,
    assessment: Assessment,
    recipient: str | None,
    config: SmtpConfig | None = None,
    store: EmailAttemptStore | None = None,
    sender: SmtpSender = _default_sender,
) -> EmailAttempt | None:
    if not recipient:
        return None
    subject = f"New Veridra audit lead: {lead.name}"
    text = (
        f"New audit lead\n\nName: {lead.name}\nEmail: {lead.email}\n"
        f"Company: {lead.company or 'Not supplied'}\nWebsite: {lead.website}\n"
        f"Consent time: {lead.consented_at.isoformat()}\n"
        f"Assessment: {lead.assessment_id}\n"
        f"Attention findings: {assessment.summary.get('attention', 0)}\n"
    )
    html_body = (
        "<h1>New audit lead</h1>"
        f"<p><strong>Name:</strong> {html.escape(lead.name)}</p>"
        f"<p><strong>Email:</strong> {html.escape(str(lead.email))}</p>"
        f"<p><strong>Company:</strong> {html.escape(lead.company or 'Not supplied')}</p>"
        f"<p><strong>Website:</strong> {html.escape(str(lead.website))}</p>"
        f"<p><strong>Assessment:</strong> {html.escape(lead.assessment_id)}</p>"
        f"<p><strong>Attention findings:</strong> {assessment.summary.get('attention', 0)}</p>"
    )
    return _send(
        kind=EmailKind.lead_notification,
        related_id=lead_id,
        assessment_id=lead.assessment_id,
        recipient=recipient,
        subject=subject,
        text_body=text,
        html_body=html_body,
        config=config,
        store=store,
        sender=sender,
    )


def send_monitoring_summary(
    *,
    project_id: str,
    project_name: str,
    target_url: str,
    assessment_id: str,
    assessment: Assessment,
    recipient: str | None,
    config: SmtpConfig | None = None,
    store: EmailAttemptStore | None = None,
    sender: SmtpSender = _default_sender,
) -> EmailAttempt | None:
    if not recipient:
        return None
    subject = f"Veridra monitoring summary: {project_name}"
    text = (
        f"Monitoring assessment completed\n\nProject: {project_name}\n"
        f"Website: {target_url}\nAssessment: {assessment_id}\n"
        f"Passed: {assessment.summary.get('passed', 0)}\n"
        f"Attention: {assessment.summary.get('attention', 0)}\n"
        f"Unavailable: {assessment.summary.get('unavailable', 0)}\n"
    )
    html_body = (
        "<h1>Monitoring assessment completed</h1>"
        f"<p><strong>Project:</strong> {html.escape(project_name)}</p>"
        f"<p><strong>Website:</strong> {html.escape(target_url)}</p>"
        f"<p><strong>Assessment:</strong> {html.escape(assessment_id)}</p>"
        f"<p><strong>Passed:</strong> {assessment.summary.get('passed', 0)}; "
        f"<strong>Attention:</strong> {assessment.summary.get('attention', 0)}; "
        f"<strong>Unavailable:</strong> {assessment.summary.get('unavailable', 0)}</p>"
    )
    return _send(
        kind=EmailKind.monitoring_summary,
        related_id=project_id,
        assessment_id=assessment_id,
        recipient=recipient,
        subject=subject,
        text_body=text,
        html_body=html_body,
        config=config,
        store=store,
        sender=sender,
    )
