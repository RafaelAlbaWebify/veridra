from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import datetime

from .stripe_billing import StripeBillingError, verify_stripe_signature

_PREVIOUS_SECRET_ENV = "VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS"


def configured_webhook_secrets(
    primary_secret: str | None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    values = os.environ if env is None else env
    previous = values.get(_PREVIOUS_SECRET_ENV, "").strip()
    if primary_secret is None:
        if previous:
            raise StripeBillingError(
                f"{_PREVIOUS_SECRET_ENV} cannot be configured when Stripe billing is disabled."
            )
        return ()
    if not primary_secret.startswith("whsec_"):
        raise StripeBillingError("Primary Stripe webhook secret is invalid.")
    if not previous:
        return (primary_secret,)
    if not previous.startswith("whsec_"):
        raise StripeBillingError(f"{_PREVIOUS_SECRET_ENV} is not a webhook secret.")
    if previous == primary_secret:
        raise StripeBillingError(
            f"{_PREVIOUS_SECRET_ENV} must differ from VERIDRA_STRIPE_WEBHOOK_SECRET."
        )
    return (primary_secret, previous)


def verify_stripe_signature_with_secrets(
    raw_body: bytes,
    signature_header: str,
    secrets: Sequence[str],
    *,
    now: datetime | None = None,
    tolerance_seconds: int = 300,
) -> None:
    if not secrets:
        raise StripeBillingError("Stripe webhook verification has no configured secret.")
    for secret in secrets:
        try:
            verify_stripe_signature(
                raw_body,
                signature_header,
                secret,
                now=now,
                tolerance_seconds=tolerance_seconds,
            )
        except StripeBillingError:
            continue
        return
    raise StripeBillingError("Stripe webhook signature is invalid.")
