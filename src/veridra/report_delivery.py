from __future__ import annotations

import hashlib
import json
import os
import smtplib
from collections.abc import Callable
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .email_delivery import EmailDeliveryError, EmailStatus, SmtpConfig, _default_sender

_MAX_MESSAGE_BYTES = 25_000_000


class ReportDeliveryAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipient: EmailStr
    attempted_at: datetime
    status: EmailStatus
    subject: str = Field(min_length=1, max_length=200)
    message_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_number: int = Field(ge=1)
    project_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    assessment_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    filename: str = Field(min_length=1, max_length=180)
    error: str = Field(default="", max_length=1000)


class ReportDeliveryStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, identifier: str) -> Path:
        if len(identifier) != 24 or any(char not in "0123456789abcdef" for char in identifier):
            raise EmailDeliveryError("Invalid report-delivery identifier.")
        return self.directory / f"{identifier}.json"

    def save(self, attempt: ReportDeliveryAttempt) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            attempt.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
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

    def list_for_project(self, project_id: str) -> list[tuple[str, ReportDeliveryAttempt]]:
        self._path(project_id)
        if not self.directory.exists():
            return []
        attempts: list[tuple[str, ReportDeliveryAttempt]] = []
        for path in self.directory.glob("*.json"):
            try:
                attempt = ReportDeliveryAttempt.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            if attempt.project_id == project_id:
                attempts.append((path.stem, attempt))
        return sorted(
            attempts,
            key=lambda item: (item[1].attempted_at, item[1].attempt_number, item[0]),
            reverse=True,
        )


ReportSender = Callable[[SmtpConfig, EmailMessage], None]


def send_report_pdf(
    *,
    project_id: str,
    assessment_id: str,
    recipient: str,
    subject: str,
    message_text: str,
    pdf_content: bytes,
    filename: str,
    store: ReportDeliveryStore,
    config: SmtpConfig | None = None,
    sender: ReportSender = _default_sender,
) -> ReportDeliveryAttempt | None:
    active = config if config is not None else SmtpConfig.from_environment()
    if active is None:
        return None
    email = EmailMessage()
    email["From"] = f"{active.sender_name} <{active.sender_email}>"
    email["To"] = recipient
    email["Subject"] = subject
    body = message_text or "Your website assessment report is attached."
    email.set_content(body)
    email.add_attachment(
        pdf_content,
        maintype="application",
        subtype="pdf",
        filename=filename,
    )
    raw = email.as_bytes()
    if len(raw) > _MAX_MESSAGE_BYTES:
        raise EmailDeliveryError("Generated report email exceeds the 25 MB delivery limit.")
    digest = hashlib.sha256(raw).hexdigest()
    prior = store.list_for_project(project_id)
    status = EmailStatus.delivered
    error = ""
    try:
        sender(active, email)
    except (OSError, smtplib.SMTPException, EmailDeliveryError, ValueError) as exc:
        status = EmailStatus.failed
        error = str(exc)[:1000]
    attempt = ReportDeliveryAttempt(
        recipient=recipient,
        attempted_at=datetime.now(UTC),
        status=status,
        subject=subject,
        message_sha256=digest,
        attempt_number=len(prior) + 1,
        project_id=project_id,
        assessment_id=assessment_id,
        filename=filename,
        error=error,
    )
    store.save(attempt)
    return attempt
