from __future__ import annotations

import argparse
import secrets
from datetime import UTC, datetime
from email.message import EmailMessage

from pydantic import EmailStr, TypeAdapter

from .email_delivery import (
    EmailAttemptStore,
    EmailDeliveryError,
    EmailStatus,
    SmtpConfig,
    _default_sender,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the configured SMTP transport with a real delivery attempt."
    )
    parser.add_argument("--recipient", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        recipient = TypeAdapter(EmailStr).validate_python(args.recipient)
        config = SmtpConfig.from_environment()
        if config is None:
            raise EmailDeliveryError("SMTP configuration is missing.")
        if config.username and config.password() is None:
            raise EmailDeliveryError(
                f"{config.password_env} is required when SMTP username is configured."
            )

        token = secrets.token_hex(6)
        message = EmailMessage()
        message["From"] = f"{config.sender_name} <{config.sender_email}>"
        message["To"] = str(recipient)
        message["Subject"] = "VERIDRA SMTP verification"
        message.set_content(
            "VERIDRA SMTP verification message.\n"
            f"Timestamp: {datetime.now(UTC).isoformat()}\n"
            f"Verification token: {token}\n"
        )
        _default_sender(config, message)

        store = EmailAttemptStore()
        print(
            "status=delivered "
            f"recipient={recipient} sender={config.sender_email} "
            f"host={config.host} port={config.port} encryption={config.encryption.value}"
        )
        print(f"verification_token={token}")
        print(f"attempt_store={store.directory}")
    except (EmailDeliveryError, ValueError, OSError) as exc:
        raise SystemExit(f"status=failed error={exc}") from exc


if __name__ == "__main__":
    main()
