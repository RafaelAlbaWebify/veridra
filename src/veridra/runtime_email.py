from __future__ import annotations

from fastapi import FastAPI

from .email_delivery import EmailDeliveryError, SmtpConfig, default_email_directory
from .identity_email_delivery import IdentityEmailAttemptStore, PasswordResetEmailAdapter
from .runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment


def configure_runtime_email(app: FastAPI, config: RuntimeConfig) -> None:
    try:
        smtp = SmtpConfig.from_environment()
    except EmailDeliveryError as exc:
        raise RuntimeConfigurationError("SMTP configuration is invalid.") from exc

    if config.environment is RuntimeEnvironment.production:
        if smtp is None:
            raise RuntimeConfigurationError(
                "VERIDRA_SMTP_HOST and VERIDRA_SMTP_SENDER are required in production."
            )
        if smtp.username and smtp.password() is None:
            raise RuntimeConfigurationError(
                f"{smtp.password_env} is required when VERIDRA_SMTP_USERNAME is configured."
            )

    if smtp is None:
        return

    if config.identity_database is not None:
        attempt_directory = config.identity_database.parent / "identity-email-deliveries"
    else:
        attempt_directory = default_email_directory() / "identity"
    app.state.veridra_smtp_config = smtp
    app.state.veridra_password_reset_delivery = PasswordResetEmailAdapter(
        config=smtp,
        store=IdentityEmailAttemptStore(attempt_directory),
        reset_origin=config.trusted_origin,
    )
