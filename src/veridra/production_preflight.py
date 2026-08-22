from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .email_delivery import EmailDeliveryError, SmtpConfig
from .runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment
from .runtime_legal import LegalLinks
from .stripe_billing import StripeBillingConfig, StripeBillingError
from .stripe_webhook_verification import configured_webhook_secrets


class PreflightStatus(StrEnum):
    ok = "ok"
    warning = "warning"
    critical = "critical"


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: PreflightStatus
    message: str


@dataclass(frozen=True)
class ProductionPreflightResult:
    status: PreflightStatus
    checks: tuple[PreflightCheck, ...]

    @property
    def ready(self) -> bool:
        return self.status is not PreflightStatus.critical

    @property
    def exit_code(self) -> int:
        return {
            PreflightStatus.ok: 0,
            PreflightStatus.warning: 1,
            PreflightStatus.critical: 2,
        }[self.status]

    def as_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "status": self.status.value,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "message": check.message,
                }
                for check in self.checks
            ],
        }


def _overall(checks: list[PreflightCheck]) -> PreflightStatus:
    if any(check.status is PreflightStatus.critical for check in checks):
        return PreflightStatus.critical
    if any(check.status is PreflightStatus.warning for check in checks):
        return PreflightStatus.warning
    return PreflightStatus.ok


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _writable_directory_or_parent(path: Path) -> bool:
    candidate = path if path.exists() else _nearest_existing_parent(path.parent)
    return (
        candidate.exists()
        and candidate.is_dir()
        and os.access(candidate, os.R_OK | os.W_OK | os.X_OK)
    )


def _storage_check(runtime: RuntimeConfig | None) -> PreflightCheck:
    if runtime is None:
        return PreflightCheck(
            name="storage",
            status=PreflightStatus.critical,
            message="Production durable-storage configuration could not be validated.",
        )
    identity = runtime.identity_database
    tenant_root = runtime.tenant_data_root
    if identity is None or tenant_root is None:
        return PreflightCheck(
            name="storage",
            status=PreflightStatus.critical,
            message="Production durable-storage paths are incomplete.",
        )
    if identity.is_relative_to(tenant_root) or tenant_root.is_relative_to(identity):
        return PreflightCheck(
            name="storage",
            status=PreflightStatus.critical,
            message="Identity and tenant durable-storage paths must be distinct.",
        )
    if identity.exists() and (
        not identity.is_file() or not os.access(identity, os.R_OK | os.W_OK)
    ):
        return PreflightCheck(
            name="storage",
            status=PreflightStatus.critical,
            message="Identity durable storage is not a readable and writable file.",
        )
    if not identity.exists() and not _writable_directory_or_parent(identity.parent):
        return PreflightCheck(
            name="storage",
            status=PreflightStatus.critical,
            message="Identity durable-storage parent is not writable.",
        )
    if tenant_root.exists() and (
        not tenant_root.is_dir()
        or not os.access(tenant_root, os.R_OK | os.W_OK | os.X_OK)
    ):
        return PreflightCheck(
            name="storage",
            status=PreflightStatus.critical,
            message="Tenant durable storage is not a readable and writable directory.",
        )
    if not tenant_root.exists() and not _writable_directory_or_parent(tenant_root):
        return PreflightCheck(
            name="storage",
            status=PreflightStatus.critical,
            message="Tenant durable-storage parent is not writable.",
        )
    return PreflightCheck(
        name="storage",
        status=PreflightStatus.ok,
        message="Production durable-storage topology is compatible with runtime and backups.",
    )


def run_production_preflight(*, require_stripe: bool = False) -> ProductionPreflightResult:
    checks: list[PreflightCheck] = []
    runtime: RuntimeConfig | None = None

    try:
        runtime = RuntimeConfig.from_environment()
    except RuntimeConfigurationError:
        checks.append(
            PreflightCheck(
                name="runtime",
                status=PreflightStatus.critical,
                message="Production runtime configuration is invalid or incomplete.",
            )
        )
    else:
        if runtime.environment is not RuntimeEnvironment.production:
            checks.append(
                PreflightCheck(
                    name="runtime",
                    status=PreflightStatus.critical,
                    message="VERIDRA_ENV must be production for production preflight.",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    name="runtime",
                    status=PreflightStatus.ok,
                    message="Production runtime configuration is valid.",
                )
            )
    checks.append(_storage_check(runtime))

    try:
        legal = LegalLinks.from_environment()
    except RuntimeConfigurationError:
        checks.append(
            PreflightCheck(
                name="legal",
                status=PreflightStatus.critical,
                message="Production legal-link configuration is invalid.",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="legal",
                status=(
                    PreflightStatus.ok if legal is not None else PreflightStatus.critical
                ),
                message=(
                    "Terms and Privacy URLs are configured."
                    if legal is not None
                    else "Terms and Privacy URLs are required for production signup."
                ),
            )
        )

    try:
        smtp = SmtpConfig.from_environment()
    except EmailDeliveryError:
        checks.append(
            PreflightCheck(
                name="smtp",
                status=PreflightStatus.critical,
                message="SMTP configuration is invalid.",
            )
        )
    else:
        if smtp is None:
            checks.append(
                PreflightCheck(
                    name="smtp",
                    status=PreflightStatus.critical,
                    message="SMTP delivery is required for production identity flows.",
                )
            )
        elif smtp.username and smtp.password() is None:
            checks.append(
                PreflightCheck(
                    name="smtp",
                    status=PreflightStatus.critical,
                    message="Configured SMTP authentication is missing its password secret.",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    name="smtp",
                    status=PreflightStatus.ok,
                    message="SMTP configuration is complete.",
                )
            )

    try:
        stripe = StripeBillingConfig.from_environment()
        configured_webhook_secrets(
            stripe.webhook_secret if stripe is not None else None
        )
    except StripeBillingError:
        checks.append(
            PreflightCheck(
                name="stripe",
                status=PreflightStatus.critical,
                message="Stripe configuration is present but invalid or incomplete.",
            )
        )
    else:
        if stripe is None:
            checks.append(
                PreflightCheck(
                    name="stripe",
                    status=(
                        PreflightStatus.critical
                        if require_stripe
                        else PreflightStatus.warning
                    ),
                    message=(
                        "Stripe billing is required but not configured."
                        if require_stripe
                        else "Stripe billing is not configured; Free-plan launch remains possible."
                    ),
                )
            )
        elif runtime is not None and runtime.trusted_origin is not None and (
            stripe.trusted_origin != runtime.trusted_origin.rstrip("/")
        ):
            checks.append(
                PreflightCheck(
                    name="stripe",
                    status=PreflightStatus.critical,
                    message="Stripe trusted origin does not match the runtime trusted origin.",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    name="stripe",
                    status=PreflightStatus.ok,
                    message="Stripe billing and webhook verification configuration are complete.",
                )
            )

    return ProductionPreflightResult(status=_overall(checks), checks=tuple(checks))
