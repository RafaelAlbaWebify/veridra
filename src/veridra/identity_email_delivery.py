from __future__ import annotations

import hashlib
import json
import os
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .email_delivery import EmailDeliveryError, EmailStatus, SmtpConfig, _default_sender
from .password_recovery_api import PasswordResetDelivery

_MAX_MESSAGE_BYTES = 128_000


class IdentityEmailKind(StrEnum):
    password_reset = "password_reset"
    tenant_invitation = "tenant_invitation"


class IdentityEmailAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: IdentityEmailKind
    recipient: EmailStr
    attempted_at: datetime
    status: EmailStatus
    subject: str = Field(min_length=1, max_length=200)
    message_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_key: str = Field(pattern=r"^[0-9a-f]{24}$")
    error: str = Field(default="", max_length=1000)


class IdentityEmailAttemptStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, identifier: str) -> Path:
        if len(identifier) != 24 or any(char not in "0123456789abcdef" for char in identifier):
            raise EmailDeliveryError("Invalid identity-email attempt identifier.")
        return self.directory / f"{identifier}.json"

    def save(self, attempt: IdentityEmailAttempt) -> str:
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

    def list(self) -> list[tuple[str, IdentityEmailAttempt]]:
        if not self.directory.exists():
            return []
        attempts: list[tuple[str, IdentityEmailAttempt]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                attempt = IdentityEmailAttempt.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            attempts.append((path.stem, attempt))
        return sorted(attempts, key=lambda item: (item[1].attempted_at, item[0]), reverse=True)


IdentityEmailSender = Callable[[SmtpConfig, EmailMessage], None]


@dataclass(frozen=True)
class TenantInvitationDelivery:
    email: str
    token: str
    expires_at: datetime


class _RecordedEmailAdapter:
    def __init__(
        self,
        *,
        config: SmtpConfig,
        store: IdentityEmailAttemptStore,
        sender: IdentityEmailSender,
    ) -> None:
        self.config = config
        self.store = store
        self.sender = sender

    def _deliver(
        self,
        *,
        kind: IdentityEmailKind,
        recipient: str,
        subject: str,
        token: str,
        message: EmailMessage,
    ) -> bool:
        raw = message.as_bytes()
        if len(raw) > _MAX_MESSAGE_BYTES:
            return False
        status = EmailStatus.delivered
        error = ""
        try:
            self.sender(self.config, message)
        except (OSError, smtplib.SMTPException, EmailDeliveryError, ValueError) as exc:
            status = EmailStatus.failed
            error = str(exc)[:1000]
        attempt = IdentityEmailAttempt(
            kind=kind,
            recipient=recipient,
            attempted_at=datetime.now(UTC),
            status=status,
            subject=subject,
            message_sha256=hashlib.sha256(raw).hexdigest(),
            delivery_key=hashlib.sha256(token.encode("utf-8")).hexdigest()[:24],
            error=error,
        )
        try:
            self.store.save(attempt)
        except (OSError, EmailDeliveryError, ValueError):
            pass
        return status is EmailStatus.delivered


class PasswordResetEmailAdapter(_RecordedEmailAdapter):
    def __init__(
        self,
        *,
        config: SmtpConfig,
        store: IdentityEmailAttemptStore,
        reset_origin: str | None = None,
        sender: IdentityEmailSender = _default_sender,
    ) -> None:
        super().__init__(config=config, store=store, sender=sender)
        self.reset_origin = reset_origin.rstrip("/") if reset_origin else None

    def __call__(self, delivery: PasswordResetDelivery) -> None:
        subject = "Reset your Veridra password"
        message = EmailMessage()
        message["From"] = f"{self.config.sender_name} <{self.config.sender_email}>"
        message["To"] = delivery.email
        message["Subject"] = subject
        if self.reset_origin:
            reset_url = f"{self.reset_origin}/reset-password?{urlencode({'token': delivery.token})}"
            instructions = f"Open this secure reset link:\n{reset_url}"
        else:
            instructions = (
                f"One-time reset token:\n{delivery.token}\n\n"
                "Submit this token with your new password to "
                "/api/auth/password-recovery/reset."
            )
        message.set_content(
            "A password reset was requested for your Veridra account.\n\n"
            f"{instructions}\n\n"
            f"Expires: {delivery.expires_at.astimezone(UTC).isoformat()}\n\n"
            "If you did not request this reset, ignore this email."
        )
        self._deliver(
            kind=IdentityEmailKind.password_reset,
            recipient=delivery.email,
            subject=subject,
            token=delivery.token,
            message=message,
        )


class TenantInvitationEmailAdapter(_RecordedEmailAdapter):
    def __init__(
        self,
        *,
        config: SmtpConfig,
        store: IdentityEmailAttemptStore,
        invitation_origin: str,
        sender: IdentityEmailSender = _default_sender,
    ) -> None:
        super().__init__(config=config, store=store, sender=sender)
        self.invitation_origin = invitation_origin.rstrip("/")

    def __call__(self, delivery: TenantInvitationDelivery) -> bool:
        subject = "You have been invited to Veridra"
        invitation_url = (
            f"{self.invitation_origin}/accept-invitation?"
            f"{urlencode({'token': delivery.token})}"
        )
        message = EmailMessage()
        message["From"] = f"{self.config.sender_name} <{self.config.sender_email}>"
        message["To"] = delivery.email
        message["Subject"] = subject
        message.set_content(
            "You have been invited to join a Veridra workspace.\n\n"
            f"Open this invitation link:\n{invitation_url}\n\n"
            f"Expires: {delivery.expires_at.astimezone(UTC).isoformat()}\n\n"
            "If you were not expecting this invitation, ignore this email."
        )
        return self._deliver(
            kind=IdentityEmailKind.tenant_invitation,
            recipient=delivery.email,
            subject=subject,
            token=delivery.token,
            message=message,
        )
