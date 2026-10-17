from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from .email_delivery import EmailDeliveryError, SmtpConfig
from .runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment
from .runtime_legal import LegalLinks


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


def _is_local_commercial_runtime(runtime: RuntimeConfig | None) -> bool:
    if runtime is None or runtime.environment is not RuntimeEnvironment.production:
        return False
    if runtime.trusted_origin is None:
        return False
    try:
        bind_ip = ipaddress.ip_address(runtime.bind_host)
    except ValueError:
        return False
    parsed = urlparse(runtime.trusted_origin)
    if parsed.hostname is None:
        return False
    if parsed.hostname.lower() == "localhost":
        origin_loopback = True
    else:
        try:
            origin_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            origin_loopback = False
    return bind_ip.is_loopback and origin_loopback


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
        if runtime.environment not in {RuntimeEnvironment.operator, RuntimeEnvironment.production}:
            checks.append(
                PreflightCheck(
                    name="runtime",
                    status=PreflightStatus.critical,
                    message="VERIDRA_ENV must be operator or production for hardened preflight.",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    name="runtime",
                    status=PreflightStatus.ok,
                    message="Hardened runtime configuration is valid.",
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
        legal_required = (
            runtime is None
            or (
                runtime.environment is RuntimeEnvironment.production
                and not _is_local_commercial_runtime(runtime)
                and not runtime.local_agency
            )
        )
        checks.append(
            PreflightCheck(
                name="legal",
                status=(
                    PreflightStatus.ok
                    if legal is not None or (runtime is not None and runtime.local_agency)
                    else (
                        PreflightStatus.critical
                        if legal_required
                        else PreflightStatus.warning
                    )
                ),
                message=(
                    "Terms and Privacy URLs are configured."
                    if legal is not None
                    else (
                        "Terms and Privacy URLs are required for public production signup."
                        if legal_required
                        else (
                            "Terms and Privacy URLs are not required for the "
                            "private Webify local-agency runtime."
                            if runtime is not None and runtime.local_agency
                            else (
                                "Terms and Privacy URLs are not configured; "
                                "local runtime may start, but public/customer-facing "
                                "legal release remains incomplete."
                            )
                        )
                    )
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
            smtp_required = (
                runtime is None
                or (
                    runtime.environment is RuntimeEnvironment.production
                    and not _is_local_commercial_runtime(runtime)
                    and not runtime.local_agency
                )
            )
            checks.append(
                PreflightCheck(
                    name="smtp",
                    status=(
                        PreflightStatus.critical
                        if smtp_required
                        else (
                            PreflightStatus.ok
                            if runtime is not None and runtime.local_agency
                            else PreflightStatus.warning
                        )
                    ),
                    message=(
                        "SMTP delivery is required for public production identity flows."
                        if smtp_required
                        else (
                            "SMTP is optional in the private Webify local-agency runtime; "
                            "email notifications remain disabled until configured."
                            if runtime is not None and runtime.local_agency
                            else (
                                "SMTP is not configured; local runtime may start, "
                                "but automated email workflows remain unverified."
                            )
                        )
                    ),
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

    # Presence Care payments are verified against the separate Webify business
    # provider/accounting workflow; VERIDRA does not sell SaaS subscriptions.
    # A legacy caller requesting VERIDRA Stripe billing must fail closed.
    checks.append(
        PreflightCheck(
            name="webify-billing-boundary",
            status=PreflightStatus.critical if require_stripe else PreflightStatus.ok,
            message=(
                "VERIDRA SaaS Stripe preflight is retired. Use Webify Presence Care "
                "provider and accounting acceptance for live charges."
                if require_stripe
                else "Webify Presence Care uses external provider/accounting authority; "
                "VERIDRA SaaS billing is not required for local operation."
            ),
        )
    )

    return ProductionPreflightResult(status=_overall(checks), checks=tuple(checks))
