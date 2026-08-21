from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from veridra.stripe_billing import (
    StripeApiClient,
    StripeBillingConfig,
    StripeBillingError,
    StripeCheckoutReservationStore,
    StripeSubscriptionAdapter,
    StripeTenantBinding,
    verify_stripe_signature,
)
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStatus, WorkspaceStore

TENANT_ID = "a" * 24
NOW = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)


def _config() -> StripeBillingConfig:
    return StripeBillingConfig(
        secret_key="sk_test_secret",
        webhook_secret="whsec_test",
        price_solo="price_solo",
        price_professional="price_professional",
        price_agency="price_agency",
        trusted_origin="https://app.example.com",
    )


def _subscription(
    *,
    subscription_id: str = "sub_current",
    customer_id: str = "cus_current",
    price_id: str = "price_agency",
    status: str = "active",
    anchor: int | None = None,
) -> dict[str, object]:
    return {
        "id": subscription_id,
        "customer": customer_id,
        "status": status,
        "billing_cycle_anchor": anchor or int(datetime(2026, 8, 31, tzinfo=UTC).timestamp()),
        "metadata": {"veridra_tenant_id": TENANT_ID},
        "items": {"data": [{"price": {"id": price_id}}]},
    }


def _event(
    *,
    event_id: str,
    event_type: str = "customer.subscription.updated",
    created: int,
    subscription: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": event_id,
        "type": event_type,
        "created": created,
        "data": {"object": subscription or _subscription()},
    }


def _workspace(tmp_path: Path) -> WorkspaceStore:
    store = WorkspaceStore(tmp_path / TENANT_ID / "workspace")
    store.save(WorkspaceConfig(display_name="Customer", plan=PlanName.free))
    return store


def test_trusted_origin_alone_does_not_enable_stripe() -> None:
    assert (
        StripeBillingConfig.from_environment(
            {"VERIDRA_TRUSTED_ORIGIN": "https://app.example.com"}
        )
        is None
    )


def test_partial_stripe_configuration_is_rejected() -> None:
    with pytest.raises(StripeBillingError, match="incomplete"):
        StripeBillingConfig.from_environment(
            {
                "VERIDRA_STRIPE_SECRET_KEY": "sk_test_secret",
                "VERIDRA_TRUSTED_ORIGIN": "https://app.example.com",
            }
        )


def test_stripe_signature_verifies_raw_body_and_rejects_tampering() -> None:
    body = b'{"id":"evt_1"}'
    timestamp = int(NOW.timestamp())
    digest = hmac.new(
        b"whsec_test",
        str(timestamp).encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    header = f"t={timestamp},v1={digest}"

    verify_stripe_signature(body, header, "whsec_test", now=NOW)

    with pytest.raises(StripeBillingError, match="signature"):
        verify_stripe_signature(body + b" ", header, "whsec_test", now=NOW)
    with pytest.raises(StripeBillingError, match="outside tolerance"):
        verify_stripe_signature(
            body,
            header,
            "whsec_test",
            now=datetime(2026, 8, 20, 16, 10, tzinfo=UTC),
        )


def test_checkout_uses_server_price_tenant_metadata_and_idempotency() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/checkout/sessions"
        form = parse_qs(request.content.decode())
        seen.update({key: values[0] for key, values in form.items()})
        seen["idempotency"] = request.headers["Idempotency-Key"]
        return httpx.Response(
            200,
            json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/test"},
        )

    client = StripeApiClient(_config(), transport=httpx.MockTransport(handler))
    session = client.create_checkout(
        tenant_id=TENANT_ID,
        customer_email="owner@example.com",
        plan=PlanName.professional,
        idempotency_key="checkout-idempotency-key",
    )

    assert session.id == "cs_test_1"
    assert seen["mode"] == "subscription"
    assert seen["line_items[0][price]"] == "price_professional"
    assert seen["client_reference_id"] == TENANT_ID
    assert seen["subscription_data[metadata][veridra_tenant_id]"] == TENANT_ID
    assert seen["subscription_data[metadata][veridra_plan]"] == "professional"
    assert seen["idempotency"] == "checkout-idempotency-key"


def test_checkout_reservation_reuses_key_and_blocks_plan_switch(tmp_path: Path) -> None:
    store = StripeCheckoutReservationStore(tmp_path)

    first = store.reserve(tenant_id=TENANT_ID, plan=PlanName.professional, now=NOW)
    repeated = store.reserve(tenant_id=TENANT_ID, plan=PlanName.professional, now=NOW)

    assert repeated.idempotency_key == first.idempotency_key
    with pytest.raises(StripeBillingError, match="different Stripe Checkout"):
        store.reserve(tenant_id=TENANT_ID, plan=PlanName.agency, now=NOW)


def test_adapter_retrieves_current_subscription_and_projects_authoritative_state(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/subscriptions/sub_current"
        return httpx.Response(200, json=_subscription(price_id="price_agency"))

    client = StripeApiClient(_config(), transport=httpx.MockTransport(handler))
    adapter = StripeSubscriptionAdapter(config=_config(), tenant_root=tmp_path, client=client)
    adapter.checkout_reservations.reserve(
        tenant_id=TENANT_ID,
        plan=PlanName.agency,
        now=NOW,
    )
    event = adapter.parse_event(
        json.dumps(
            _event(
                event_id="evt_created",
                event_type="customer.subscription.created",
                created=int(NOW.timestamp()),
            )
        ).encode()
    )

    result = adapter.handle(event)

    assert result.handled is True
    assert result.applied is True
    assert workspace.load().plan is PlanName.agency
    assert workspace.load().status is WorkspaceStatus.active
    assert workspace.load().cycle_anchor_day == 28
    binding = adapter.bindings.load(TENANT_ID)
    assert binding is not None
    assert binding.customer_id == "cus_current"
    assert binding.subscription_id == "sub_current"
    assert adapter.checkout_reservations.load(TENANT_ID) is None


def test_delayed_webhook_cannot_roll_back_newer_current_stripe_state(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    current_price = "price_agency"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_subscription(price_id=current_price))

    client = StripeApiClient(_config(), transport=httpx.MockTransport(handler))
    adapter = StripeSubscriptionAdapter(config=_config(), tenant_root=tmp_path, client=client)

    first = adapter.parse_event(
        json.dumps(_event(event_id="evt_200", created=200)).encode()
    )
    adapter.handle(first)
    assert workspace.load().plan is PlanName.agency

    delayed = adapter.parse_event(
        json.dumps(
            _event(
                event_id="evt_150",
                created=150,
                subscription=_subscription(price_id="price_solo"),
            )
        ).encode()
    )
    result = adapter.handle(delayed)

    assert result.applied is False
    assert workspace.load().plan is PlanName.agency


def test_old_subscription_deletion_cannot_suspend_replacement(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.save(
        WorkspaceConfig(
            display_name="Customer",
            plan=PlanName.professional,
            status=WorkspaceStatus.active,
        )
    )
    adapter = StripeSubscriptionAdapter(config=_config(), tenant_root=tmp_path)
    adapter.bindings.save(
        StripeTenantBinding(
            tenant_id=TENANT_ID,
            customer_id="cus_new",
            subscription_id="sub_new",
            updated_at=NOW,
        )
    )
    deletion = adapter.parse_event(
        json.dumps(
            _event(
                event_id="evt_delete_old",
                event_type="customer.subscription.deleted",
                created=int(NOW.timestamp()),
                subscription=_subscription(
                    subscription_id="sub_old",
                    customer_id="cus_old",
                    price_id="price_solo",
                    status="canceled",
                ),
            )
        ).encode()
    )

    result = adapter.handle(deletion)

    assert result.handled is True
    assert result.applied is False
    assert workspace.load().status is WorkspaceStatus.active
    assert adapter.bindings.load(TENANT_ID).subscription_id == "sub_new"  # type: ignore[union-attr]
