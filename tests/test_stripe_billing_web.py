from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import bind_verified_request_identity
from veridra.runtime_billing import StripeBillingRuntime
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.stripe_billing import (
    StripeApiClient,
    StripeBillingConfig,
    StripeSubscriptionAdapter,
    StripeTenantBinding,
)
from veridra.stripe_billing_web import router
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore

ORIGIN = "https://app.example.com"


def _config() -> StripeBillingConfig:
    return StripeBillingConfig(
        secret_key="sk_test_secret",
        webhook_secret="whsec_test",
        price_solo="price_solo",
        price_professional="price_professional",
        price_agency="price_agency",
        trusted_origin=ORIGIN,
    )


def _client(tmp_path: Path) -> tuple[TestClient, StripeSubscriptionAdapter, RequestIdentity]:
    database = tmp_path / "identity.sqlite3"
    tenant_root = tmp_path / "tenants"
    created = SQLiteIdentityBootstrap(database, tenant_data_root=tenant_root).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password="owner-correct-horse-battery",
        confirmation=BOOTSTRAP_CONFIRMATION,
    )
    WorkspaceStore(tenant_root / created.tenant_id / "workspace").save(
        WorkspaceConfig(display_name="Customer one", plan=PlanName.free)
    )
    owner = RequestIdentity(
        user_id=created.user_id,
        tenant_id=created.tenant_id,
        membership_role=TenantRole.owner,
        session_id="1" * 24,
        authenticated_at=datetime.now(UTC),
    )
    viewer = RequestIdentity(
        user_id=created.user_id,
        tenant_id=created.tenant_id,
        membership_role=TenantRole.viewer,
        session_id="2" * 24,
        authenticated_at=datetime.now(UTC),
    )

    def stripe_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/checkout/sessions":
            return httpx.Response(
                200,
                json={"id": "cs_test", "url": "https://checkout.stripe.com/c/pay/test"},
            )
        if request.url.path == "/v1/billing_portal/sessions":
            return httpx.Response(
                200,
                json={"id": "bps_test", "url": "https://billing.stripe.com/p/session/test"},
            )
        if request.url.path.startswith("/v1/subscriptions/"):
            return httpx.Response(
                200,
                json={
                    "id": "sub_current",
                    "customer": "cus_current",
                    "status": "active",
                    "billing_cycle_anchor": int(datetime(2026, 8, 20, tzinfo=UTC).timestamp()),
                    "metadata": {"veridra_tenant_id": created.tenant_id},
                    "items": {"data": [{"price": {"id": "price_professional"}}]},
                },
            )
        raise AssertionError(f"Unexpected Stripe request: {request.url}")

    config = _config()
    stripe_client = StripeApiClient(config, transport=httpx.MockTransport(stripe_handler))
    adapter = StripeSubscriptionAdapter(
        config=config,
        tenant_root=tenant_root,
        client=stripe_client,
    )
    app = FastAPI()
    app.state.veridra_identity_store = SQLiteIdentityRecordStore(database)
    app.state.veridra_tenant_data_root = tenant_root
    app.state.veridra_stripe_billing = StripeBillingRuntime(config, stripe_client, adapter)

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.headers.get("x-test-role") == "owner":
            bind_verified_request_identity(request, owner)
        elif request.headers.get("x-test-role") == "viewer":
            bind_verified_request_identity(request, viewer)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app, base_url=ORIGIN), adapter, owner


def test_billing_page_requires_tenant_management_capability(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)

    assert client.get("/billing").status_code == 401
    assert client.get("/billing", headers={"x-test-role": "viewer"}).status_code == 403
    owner = client.get("/billing", headers={"x-test-role": "owner"})
    assert owner.status_code == 200
    assert "Current Veridra plan:</strong> Free" in owner.text
    assert "Stripe-hosted Checkout" in owner.text


def test_checkout_is_same_origin_and_redirects_to_stripe(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)

    missing_origin = client.post(
        "/billing/checkout/professional",
        headers={"x-test-role": "owner"},
        follow_redirects=False,
    )
    assert missing_origin.status_code == 403

    checkout = client.post(
        "/billing/checkout/professional",
        headers={"x-test-role": "owner", "origin": ORIGIN},
        follow_redirects=False,
    )
    assert checkout.status_code == 303
    assert checkout.headers["location"].startswith("https://checkout.stripe.com/")


def test_existing_subscription_uses_portal_and_blocks_duplicate_checkout(tmp_path: Path) -> None:
    client, adapter, owner = _client(tmp_path)
    adapter.bindings.save(
        StripeTenantBinding(
            tenant_id=owner.tenant_id,
            customer_id="cus_current",
            subscription_id="sub_current",
            updated_at=datetime.now(UTC),
        )
    )

    duplicate = client.post(
        "/billing/checkout/agency",
        headers={"x-test-role": "owner", "origin": ORIGIN},
        follow_redirects=False,
    )
    assert duplicate.status_code == 409

    portal = client.post(
        "/billing/portal",
        headers={"x-test-role": "owner", "origin": ORIGIN},
        follow_redirects=False,
    )
    assert portal.status_code == 303
    assert portal.headers["location"].startswith("https://billing.stripe.com/")


def test_webhook_requires_valid_signature_and_projects_subscription(tmp_path: Path) -> None:
    client, _, owner = _client(tmp_path)
    now = datetime.now(UTC)
    payload = json.dumps(
        {
            "id": "evt_current",
            "type": "customer.subscription.updated",
            "created": int(now.timestamp()),
            "data": {
                "object": {
                    "id": "sub_current",
                    "customer": "cus_current",
                    "status": "active",
                    "billing_cycle_anchor": int(now.timestamp()),
                    "metadata": {"veridra_tenant_id": owner.tenant_id},
                    "items": {"data": [{"price": {"id": "price_solo"}}]},
                }
            },
        },
        separators=(",", ":"),
    ).encode()

    rejected = client.post(
        "/api/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": "t=1,v1=bad"},
    )
    assert rejected.status_code == 400

    timestamp = int(now.timestamp())
    digest = hmac.new(
        b"whsec_test",
        str(timestamp).encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    accepted = client.post(
        "/api/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": f"t={timestamp},v1={digest}"},
    )
    assert accepted.status_code == 200
    assert accepted.json() == {"received": True, "handled": True, "applied": True}

    workspace = WorkspaceStore(tmp_path / "tenants" / owner.tenant_id / "workspace").load()
    assert workspace.plan is PlanName.professional
