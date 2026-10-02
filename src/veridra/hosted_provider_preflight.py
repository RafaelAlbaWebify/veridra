from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .email_delivery import EmailDeliveryError, SmtpConfig
from .stripe_billing import StripeApiClient, StripeBillingConfig, StripeBillingError
from .workspace_policy import PlanName


class HostedProviderPreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class StripePlanCheck:
    plan: str
    price_id: str
    active: bool
    recurring_interval: str


@dataclass(frozen=True)
class HostedProviderPreflightResult:
    stripe_test_mode: bool
    trusted_origin: str
    stripe_plans: tuple[StripePlanCheck, ...]
    smtp_configured: bool
    smtp_host: str | None
    smtp_port: int | None
    smtp_encryption: str | None
    smtp_sender_domain: str | None

    def evidence(self) -> dict[str, object]:
        return {
            "contract": "veridra_local_commercial_provider_preflight",
            "version": "1.0",
            "stripe": {
                "test_mode": self.stripe_test_mode,
                "trusted_origin": self.trusted_origin,
                "plans": [
                    {
                        "plan": item.plan,
                        "price_id": item.price_id,
                        "active": item.active,
                        "recurring_interval": item.recurring_interval,
                    }
                    for item in self.stripe_plans
                ],
            },
            "smtp": {
                "configured": self.smtp_configured,
                "host": self.smtp_host,
                "port": self.smtp_port,
                "encryption": self.smtp_encryption,
                "sender_domain": self.smtp_sender_domain,
            },
            "secrets_included": False,
        }


def _sender_domain(config: SmtpConfig) -> str:
    return str(config.sender_email).rsplit("@", 1)[-1].lower()


def run_hosted_provider_preflight(
    *,
    env: Mapping[str, str] | None = None,
    stripe_client: StripeApiClient | None = None,
) -> HostedProviderPreflightResult:
    try:
        stripe_config = StripeBillingConfig.from_environment(env)
    except StripeBillingError as exc:
        raise HostedProviderPreflightError(str(exc)) from exc
    if stripe_config is None:
        raise HostedProviderPreflightError("Stripe billing configuration is missing.")
    if not stripe_config.secret_key.startswith("sk_test_"):
        raise HostedProviderPreflightError(
            "Hosted provider acceptance must use a Stripe test-mode secret key."
        )
    parsed_origin = urlparse(stripe_config.trusted_origin)
    loopback_origin = (
        parsed_origin.hostname == "localhost"
        or parsed_origin.hostname in {"127.0.0.1", "::1"}
    )
    if parsed_origin.scheme != "https" and not (
        parsed_origin.scheme == "http" and loopback_origin
    ):
        raise HostedProviderPreflightError(
            "Provider acceptance requires HTTPS or an explicit HTTP loopback origin."
        )

    client = stripe_client or StripeApiClient(stripe_config)
    plan_checks: list[StripePlanCheck] = []
    for plan in (PlanName.solo, PlanName.professional, PlanName.agency):
        price_id = stripe_config.price_for_plan(plan)
        try:
            price = client.retrieve_price(price_id)
        except StripeBillingError as exc:
            raise HostedProviderPreflightError(
                f"Stripe Price for {plan.value} could not be verified."
            ) from exc
        if price.livemode:
            raise HostedProviderPreflightError(
                f"Stripe Price for {plan.value} is live-mode; test-mode is required."
            )
        if not price.active:
            raise HostedProviderPreflightError(
                f"Stripe Price for {plan.value} is not active."
            )
        if price.type != "recurring" or price.recurring is None:
            raise HostedProviderPreflightError(
                f"Stripe Price for {plan.value} is not recurring."
            )
        plan_checks.append(
            StripePlanCheck(
                plan=plan.value,
                price_id=price.id,
                active=price.active,
                recurring_interval=price.recurring.interval,
            )
        )

    try:
        smtp = SmtpConfig.from_environment(env)
    except EmailDeliveryError as exc:
        raise HostedProviderPreflightError(str(exc)) from exc

    return HostedProviderPreflightResult(
        stripe_test_mode=True,
        trusted_origin=stripe_config.trusted_origin,
        stripe_plans=tuple(plan_checks),
        smtp_configured=smtp is not None,
        smtp_host=smtp.host if smtp is not None else None,
        smtp_port=smtp.port if smtp is not None else None,
        smtp_encryption=smtp.encryption.value if smtp is not None else None,
        smtp_sender_domain=_sender_domain(smtp) if smtp is not None else None,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate local-commercial Stripe test-mode Price configuration and optional SMTP "
            "configuration without exposing provider secrets."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON evidence path. Parent directories are created automatically.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        result = run_hosted_provider_preflight()
    except HostedProviderPreflightError as exc:
        raise SystemExit(f"status=failed error={exc}") from exc
    payload = result.evidence()
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
