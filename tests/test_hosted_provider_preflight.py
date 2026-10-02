from __future__ import annotations

import json

import httpx
import pytest

from veridra.hosted_provider_preflight import (
    HostedProviderPreflightError,
    run_hosted_provider_preflight,
)
from veridra.stripe_billing import StripeApiClient, StripeBillingConfig


def _env() -> dict[str, str]:
    return {
        "VERIDRA_STRIPE_SECRET_KEY": "sk_test_provider",
        "VERIDRA_STRIPE_WEBHOOK_SECRET": "whsec_provider",
        "VERIDRA_STRIPE_PRICE_SOLO": "price_solo",
        "VERIDRA_STRIPE_PRICE_PROFESSIONAL": "price_professional",
        "VERIDRA_STRIPE_PRICE_AGENCY": "price_agency",
        "VERIDRA_TRUSTED_ORIGIN": "https://app.example.com",
    }


def _client(
    env: dict[str, str],
    *,
    live_price: str | None = None,
    inactive_price: str | None = None,
    one_time_price: str | None = None,
) -> StripeApiClient:
    config = StripeBillingConfig.from_environment(env)
    assert config is not None

    def handler(request: httpx.Request) -> httpx.Response:
        price_id = request.url.path.rsplit("/", 1)[-1]
        assert price_id in {
            "price_solo",
            "price_professional",
            "price_agency",
        }
        recurring = None if price_id == one_time_price else {"interval": "month"}
        return httpx.Response(
            200,
            json={
                "id": price_id,
                "active": price_id != inactive_price,
                "type": "one_time" if price_id == one_time_price else "recurring",
                "livemode": price_id == live_price,
                "recurring": recurring,
            },
        )

    return StripeApiClient(config, transport=httpx.MockTransport(handler))


def test_hosted_provider_preflight_verifies_test_prices_without_secrets() -> None:
    env = _env()
    result = run_hosted_provider_preflight(
        env=env,
        stripe_client=_client(env),
    )

    evidence = result.evidence()

    assert result.stripe_test_mode is True
    assert [item.plan for item in result.stripe_plans] == [
        "solo",
        "professional",
        "agency",
    ]
    assert all(item.active for item in result.stripe_plans)
    assert all(item.recurring_interval == "month" for item in result.stripe_plans)
    assert result.smtp_configured is False
    assert evidence["secrets_included"] is False
    rendered = json.dumps(evidence)
    assert "sk_test_provider" not in rendered
    assert "whsec_provider" not in rendered


def test_hosted_provider_preflight_reports_optional_smtp_without_credentials() -> None:
    env = {
        **_env(),
        "VERIDRA_SMTP_HOST": "smtp.example.com",
        "VERIDRA_SMTP_PORT": "587",
        "VERIDRA_SMTP_ENCRYPTION": "starttls",
        "VERIDRA_SMTP_SENDER": "reports@agency.example",
        "VERIDRA_SMTP_SENDER_NAME": "Agency Reports",
        "VERIDRA_SMTP_USERNAME": "smtp-user",
        "VERIDRA_SMTP_PASSWORD_ENV": "VERIDRA_SMTP_PASSWORD",
        "VERIDRA_SMTP_PASSWORD": "super-secret-password",
    }

    result = run_hosted_provider_preflight(
        env=env,
        stripe_client=_client(env),
    )
    rendered = json.dumps(result.evidence())

    assert result.smtp_configured is True
    assert result.smtp_host == "smtp.example.com"
    assert result.smtp_port == 587
    assert result.smtp_encryption == "starttls"
    assert result.smtp_sender_domain == "agency.example"
    assert "smtp-user" not in rendered
    assert "super-secret-password" not in rendered
    assert "reports@agency.example" not in rendered


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda env: env.__setitem__(
                "VERIDRA_STRIPE_SECRET_KEY",
                "sk_live_provider",
            ),
            "test-mode secret key",
        ),
        (
            lambda env: env.__setitem__(
                "VERIDRA_TRUSTED_ORIGIN",
                "http://app.example.com",
            ),
            "HTTPS trusted origin",
        ),
    ],
)
def test_hosted_provider_preflight_rejects_unsafe_acceptance_configuration(
    mutator: object,
    message: str,
) -> None:
    env = _env()
    assert callable(mutator)
    mutator(env)

    with pytest.raises(HostedProviderPreflightError, match=message):
        run_hosted_provider_preflight(
            env=env,
            stripe_client=_client(_env()),
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"live_price": "price_agency"}, "live-mode"),
        ({"inactive_price": "price_professional"}, "not active"),
        ({"one_time_price": "price_solo"}, "not recurring"),
    ],
)
def test_hosted_provider_preflight_rejects_invalid_price_configuration(
    kwargs: dict[str, str],
    message: str,
) -> None:
    env = _env()

    with pytest.raises(HostedProviderPreflightError, match=message):
        run_hosted_provider_preflight(
            env=env,
            stripe_client=_client(env, **kwargs),
        )
