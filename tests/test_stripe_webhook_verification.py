from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

import pytest

from veridra.stripe_billing import StripeBillingError
from veridra.stripe_webhook_verification import (
    configured_webhook_secrets,
    verify_stripe_signature_with_secrets,
)

NOW = datetime(2026, 8, 20, 16, 45, tzinfo=UTC)


def _header(body: bytes, secret: str) -> str:
    timestamp = int(NOW.timestamp())
    digest = hmac.new(
        secret.encode("utf-8"),
        str(timestamp).encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_single_primary_secret_is_configured() -> None:
    assert configured_webhook_secrets("whsec_current", env={}) == ("whsec_current",)


def test_previous_secret_is_optional_rotation_overlap() -> None:
    assert configured_webhook_secrets(
        "whsec_current",
        env={"VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS": "whsec_previous"},
    ) == ("whsec_current", "whsec_previous")


def test_previous_secret_cannot_enable_stripe_by_itself() -> None:
    with pytest.raises(StripeBillingError, match="cannot be configured"):
        configured_webhook_secrets(
            None,
            env={"VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS": "whsec_previous"},
        )


def test_previous_secret_must_be_valid_and_distinct() -> None:
    with pytest.raises(StripeBillingError, match="not a webhook secret"):
        configured_webhook_secrets(
            "whsec_current",
            env={"VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS": "bad"},
        )
    with pytest.raises(StripeBillingError, match="must differ"):
        configured_webhook_secrets(
            "whsec_current",
            env={"VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS": "whsec_current"},
        )


def test_signature_verification_accepts_current_secret() -> None:
    body = b'{"id":"evt_current"}'

    verify_stripe_signature_with_secrets(
        body,
        _header(body, "whsec_current"),
        ("whsec_current", "whsec_previous"),
        now=NOW,
    )


def test_signature_verification_accepts_previous_secret_during_overlap() -> None:
    body = b'{"id":"evt_previous"}'

    verify_stripe_signature_with_secrets(
        body,
        _header(body, "whsec_previous"),
        ("whsec_current", "whsec_previous"),
        now=NOW,
    )


def test_signature_verification_rejects_unknown_secret() -> None:
    body = b'{"id":"evt_unknown"}'

    with pytest.raises(StripeBillingError, match="signature"):
        verify_stripe_signature_with_secrets(
            body,
            _header(body, "whsec_unknown"),
            ("whsec_current", "whsec_previous"),
            now=NOW,
        )


def test_signature_verification_keeps_timestamp_tolerance() -> None:
    body = b'{"id":"evt_stale"}'

    with pytest.raises(StripeBillingError, match="signature"):
        verify_stripe_signature_with_secrets(
            body,
            _header(body, "whsec_previous"),
            ("whsec_current", "whsec_previous"),
            now=datetime(2026, 8, 20, 17, 0, tzinfo=UTC),
        )
