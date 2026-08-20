from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from .runtime_config import RuntimeConfig, RuntimeConfigurationError
from .stripe_billing import (
    StripeApiClient,
    StripeBillingConfig,
    StripeBillingError,
    StripeSubscriptionAdapter,
)


@dataclass(frozen=True)
class StripeBillingRuntime:
    config: StripeBillingConfig
    client: StripeApiClient
    adapter: StripeSubscriptionAdapter


def configure_runtime_billing(app: FastAPI, runtime: RuntimeConfig) -> None:
    try:
        config = StripeBillingConfig.from_environment()
    except StripeBillingError as exc:
        raise RuntimeConfigurationError("Stripe billing configuration is invalid.") from exc
    if config is None:
        return
    if runtime.tenant_data_root is None:
        raise RuntimeConfigurationError(
            "VERIDRA_TENANT_DATA_ROOT is required when Stripe billing is enabled."
        )
    if runtime.trusted_origin is None or config.trusted_origin != runtime.trusted_origin.rstrip("/"):
        raise RuntimeConfigurationError(
            "Stripe billing must use the configured VERIDRA_TRUSTED_ORIGIN."
        )
    client = StripeApiClient(config)
    app.state.veridra_stripe_billing = StripeBillingRuntime(
        config=config,
        client=client,
        adapter=StripeSubscriptionAdapter(
            config=config,
            tenant_root=runtime.tenant_data_root,
            client=client,
        ),
    )
