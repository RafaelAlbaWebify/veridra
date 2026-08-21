from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .email_delivery import EmailDeliveryError, SmtpConfig
from .runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment
from .runtime_legal import LegalLinks
from .stripe_billing import StripeBillingConfig, StripeBillingError


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
                    message="Stripe billing configuration is complete.",
                )
            )

    return ProductionPreflightResult(status=_overall(checks), checks=tuple(checks))
