from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .subscription_authority import (
    SubscriptionApplyResult,
    SubscriptionAuthority,
    SubscriptionAuthorityError,
    SubscriptionUpdate,
)
from .workspace_policy import PlanName, WorkspaceStatus, WorkspaceStore


class StripeBillingError(RuntimeError):
    pass


@dataclass(frozen=True)
class StripeBillingConfig:
    secret_key: str = field(repr=False)
    webhook_secret: str = field(repr=False)
    price_solo: str
    price_professional: str
    price_agency: str
    trusted_origin: str

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> StripeBillingConfig | None:
        values = os.environ if env is None else env
        stripe_names = (
            "VERIDRA_STRIPE_SECRET_KEY",
            "VERIDRA_STRIPE_WEBHOOK_SECRET",
            "VERIDRA_STRIPE_PRICE_SOLO",
            "VERIDRA_STRIPE_PRICE_PROFESSIONAL",
            "VERIDRA_STRIPE_PRICE_AGENCY",
        )
        stripe_values = {name: values.get(name, "").strip() for name in stripe_names}
        if not any(stripe_values.values()):
            return None
        configured = {
            **stripe_values,
            "VERIDRA_TRUSTED_ORIGIN": values.get("VERIDRA_TRUSTED_ORIGIN", "").strip(),
        }
        missing = [name for name, value in configured.items() if not value]
        if missing:
            raise StripeBillingError(
                "Stripe billing configuration is incomplete: " + ", ".join(sorted(missing))
            )
        secret_key = configured["VERIDRA_STRIPE_SECRET_KEY"]
        webhook_secret = configured["VERIDRA_STRIPE_WEBHOOK_SECRET"]
        if not secret_key.startswith(("sk_test_", "sk_live_")):
            raise StripeBillingError("VERIDRA_STRIPE_SECRET_KEY is not a Stripe secret key.")
        if not webhook_secret.startswith("whsec_"):
            raise StripeBillingError("VERIDRA_STRIPE_WEBHOOK_SECRET is not a webhook secret.")
        prices = (
            configured["VERIDRA_STRIPE_PRICE_SOLO"],
            configured["VERIDRA_STRIPE_PRICE_PROFESSIONAL"],
            configured["VERIDRA_STRIPE_PRICE_AGENCY"],
        )
        if any(not price.startswith("price_") for price in prices):
            raise StripeBillingError("Stripe plan mappings must contain Stripe Price IDs.")
        if len(set(prices)) != len(prices):
            raise StripeBillingError("Stripe plan Price IDs must be distinct.")
        return cls(
            secret_key=secret_key,
            webhook_secret=webhook_secret,
            price_solo=prices[0],
            price_professional=prices[1],
            price_agency=prices[2],
            trusted_origin=configured["VERIDRA_TRUSTED_ORIGIN"].rstrip("/"),
        )

    def price_for_plan(self, plan: PlanName) -> str:
        try:
            return {
                PlanName.solo: self.price_solo,
                PlanName.professional: self.price_professional,
                PlanName.agency: self.price_agency,
            }[plan]
        except KeyError as exc:
            raise StripeBillingError("The free plan does not have a paid checkout Price.") from exc

    def plan_for_price(self, price_id: str) -> PlanName:
        mapping = {
            self.price_solo: PlanName.solo,
            self.price_professional: PlanName.professional,
            self.price_agency: PlanName.agency,
        }
        try:
            return mapping[price_id]
        except KeyError as exc:
            raise StripeBillingError("Stripe subscription contains an unmapped Price ID.") from exc


class StripeCheckoutSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    url: str = Field(min_length=1)


class StripePortalSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    url: str = Field(min_length=1)


class StripePrice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)


class StripeSubscriptionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price: StripePrice


class StripeSubscriptionItems(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[StripeSubscriptionItem]


class StripeSubscription(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    customer: str = Field(min_length=1)
    status: str = Field(min_length=1)
    billing_cycle_anchor: int = Field(ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)
    items: StripeSubscriptionItems


class StripeWebhookData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object: dict[str, object]


class StripeWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    created: int = Field(ge=0)
    data: StripeWebhookData


class StripeTenantBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    customer_id: str = Field(min_length=1, max_length=160)
    subscription_id: str = Field(min_length=1, max_length=160)
    updated_at: datetime


class StripeCheckoutReservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    plan: PlanName
    idempotency_key: str = Field(min_length=24, max_length=255)
    created_at: datetime
    expires_at: datetime


class StripeTenantBindingStore:
    def __init__(self, tenant_root: Path) -> None:
        self.tenant_root = tenant_root

    def _path(self, tenant_id: str) -> Path:
        if len(tenant_id) != 24 or any(char not in "0123456789abcdef" for char in tenant_id):
            raise StripeBillingError("Tenant identifier is invalid.")
        return self.tenant_root / tenant_id / "workspace" / "billing" / "stripe.json"

    def load(self, tenant_id: str) -> StripeTenantBinding | None:
        path = self._path(tenant_id)
        if not path.exists():
            return None
        try:
            return StripeTenantBinding.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StripeBillingError("Stripe tenant binding could not be read safely.") from exc

    def save(self, binding: StripeTenantBinding) -> None:
        path = self._path(binding.tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            binding.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".stripe.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)


class StripeCheckoutReservationStore:
    def __init__(self, tenant_root: Path) -> None:
        self.tenant_root = tenant_root

    def _path(self, tenant_id: str) -> Path:
        if len(tenant_id) != 24 or any(char not in "0123456789abcdef" for char in tenant_id):
            raise StripeBillingError("Tenant identifier is invalid.")
        return (
            self.tenant_root
            / tenant_id
            / "workspace"
            / "billing"
            / "checkout-reservation.json"
        )

    def load(self, tenant_id: str) -> StripeCheckoutReservation | None:
        path = self._path(tenant_id)
        if not path.exists():
            return None
        try:
            return StripeCheckoutReservation.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise StripeBillingError(
                "Stripe Checkout reservation could not be read safely."
            ) from exc

    def reserve(
        self,
        *,
        tenant_id: str,
        plan: PlanName,
        now: datetime | None = None,
        lifetime: timedelta = timedelta(minutes=30),
    ) -> StripeCheckoutReservation:
        if lifetime <= timedelta(0):
            raise ValueError("Stripe Checkout reservation lifetime must be positive.")
        checked_at = (now or datetime.now(UTC)).astimezone(UTC)
        path = self._path(tenant_id)
        for _ in range(4):
            current = self.load(tenant_id)
            if current is not None:
                if current.expires_at > checked_at:
                    if current.plan is not plan:
                        raise StripeBillingError(
                            "A different Stripe Checkout is already in progress."
                        )
                    return current
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise StripeBillingError(
                        "Expired Stripe Checkout reservation could not be cleared."
                    ) from exc

            reservation = StripeCheckoutReservation(
                tenant_id=tenant_id,
                plan=plan,
                idempotency_key=(
                    f"veridra-checkout-{tenant_id}-{secrets.token_hex(16)}"
                ),
                created_at=checked_at,
                expires_at=checked_at + lifetime,
            )
            content = json.dumps(
                reservation.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                continue
            except OSError as exc:
                raise StripeBillingError(
                    "Stripe Checkout reservation could not be created."
                ) from exc
            try:
                os.write(descriptor, content)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return reservation
        raise StripeBillingError("Stripe Checkout reservation could not be acquired.")

    def clear(self, tenant_id: str) -> None:
        try:
            self._path(tenant_id).unlink(missing_ok=True)
        except OSError as exc:
            raise StripeBillingError(
                "Stripe Checkout reservation could not be cleared."
            ) from exc


class StripeApiClient:
    def __init__(
        self,
        config: StripeBillingConfig,
        *,
        base_url: str = "https://api.stripe.com",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        try:
            with httpx.Client(
                base_url=self.base_url,
                auth=(self.config.secret_key, ""),
                timeout=15.0,
                transport=self.transport,
            ) as client:
                response = client.request(method, path, data=data, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StripeBillingError("Stripe API request failed.") from exc
        if not isinstance(payload, dict):
            raise StripeBillingError("Stripe API returned an invalid response.")
        return cast(dict[str, object], payload)

    def create_checkout(
        self,
        *,
        tenant_id: str,
        customer_email: str,
        plan: PlanName,
        idempotency_key: str | None = None,
    ) -> StripeCheckoutSession:
        price_id = self.config.price_for_plan(plan)
        payload = self._request(
            "POST",
            "/v1/checkout/sessions",
            data={
                "mode": "subscription",
                "success_url": f"{self.config.trusted_origin}/billing?checkout=success",
                "cancel_url": f"{self.config.trusted_origin}/billing?checkout=cancelled",
                "client_reference_id": tenant_id,
                "customer_email": customer_email,
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "subscription_data[metadata][veridra_tenant_id]": tenant_id,
                "subscription_data[metadata][veridra_plan]": plan.value,
            },
            idempotency_key=idempotency_key,
        )
        try:
            return StripeCheckoutSession.model_validate(payload)
        except ValidationError as exc:
            raise StripeBillingError("Stripe Checkout response is invalid.") from exc

    def create_portal(self, *, customer_id: str) -> StripePortalSession:
        payload = self._request(
            "POST",
            "/v1/billing_portal/sessions",
            data={
                "customer": customer_id,
                "return_url": f"{self.config.trusted_origin}/billing",
            },
        )
        try:
            return StripePortalSession.model_validate(payload)
        except ValidationError as exc:
            raise StripeBillingError("Stripe Billing Portal response is invalid.") from exc

    def retrieve_subscription(self, subscription_id: str) -> StripeSubscription:
        payload = self._request("GET", f"/v1/subscriptions/{subscription_id}")
        try:
            return StripeSubscription.model_validate(payload)
        except ValidationError as exc:
            raise StripeBillingError("Stripe subscription response is invalid.") from exc


def verify_stripe_signature(
    raw_body: bytes,
    signature_header: str,
    secret: str,
    *,
    now: datetime | None = None,
    tolerance_seconds: int = 300,
) -> None:
    if tolerance_seconds < 1:
        raise ValueError("Signature tolerance must be positive.")
    timestamp: int | None = None
    signatures: list[str] = []
    for component in signature_header.split(","):
        key, separator, value = component.strip().partition("=")
        if not separator:
            continue
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                timestamp = None
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        raise StripeBillingError("Stripe webhook signature is invalid.")
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if abs(int(checked_at.timestamp()) - timestamp) > tolerance_seconds:
        raise StripeBillingError("Stripe webhook signature timestamp is outside tolerance.")
    signed_payload = str(timestamp).encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise StripeBillingError("Stripe webhook signature is invalid.")


@dataclass(frozen=True)
class StripeWebhookResult:
    handled: bool
    applied: bool
    tenant_id: str = ""
    reason: str = ""


class StripeSubscriptionAdapter:
    _SUBSCRIPTION_EVENTS = frozenset(
        {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }
    )

    def __init__(
        self,
        *,
        config: StripeBillingConfig,
        tenant_root: Path,
        client: StripeApiClient | None = None,
    ) -> None:
        self.config = config
        self.tenant_root = tenant_root
        self.client = client or StripeApiClient(config)
        self.bindings = StripeTenantBindingStore(tenant_root)
        self.checkout_reservations = StripeCheckoutReservationStore(tenant_root)
        self.authority = SubscriptionAuthority(tenant_root)

    def parse_event(self, raw_body: bytes) -> StripeWebhookEvent:
        try:
            payload = json.loads(raw_body)
            return StripeWebhookEvent.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise StripeBillingError("Stripe webhook payload is invalid.") from exc

    @staticmethod
    def _workspace_status(stripe_status: str) -> WorkspaceStatus:
        return (
            WorkspaceStatus.active
            if stripe_status in {"active", "trialing"}
            else WorkspaceStatus.suspended
        )

    def _plan(self, subscription: StripeSubscription) -> PlanName:
        plans = {
            self.config.plan_for_price(item.price.id)
            for item in subscription.items.data
        }
        if len(plans) != 1:
            raise StripeBillingError("Stripe subscription must map to exactly one Veridra plan.")
        return plans.pop()

    @staticmethod
    def _tenant_id(subscription: StripeSubscription) -> str:
        tenant_id = subscription.metadata.get("veridra_tenant_id", "").strip().lower()
        if len(tenant_id) != 24 or any(char not in "0123456789abcdef" for char in tenant_id):
            raise StripeBillingError(
                "Stripe subscription is missing valid Veridra tenant metadata."
            )
        return tenant_id

    def _update(
        self,
        *,
        event: StripeWebhookEvent,
        subscription: StripeSubscription,
    ) -> SubscriptionUpdate:
        anchor = datetime.fromtimestamp(subscription.billing_cycle_anchor, tz=UTC).day
        return SubscriptionUpdate(
            tenant_id=self._tenant_id(subscription),
            provider="stripe",
            provider_event_id=event.id,
            external_subscription_id=subscription.id,
            plan=self._plan(subscription),
            status=self._workspace_status(subscription.status),
            cycle_anchor_day=min(anchor, 28),
            occurred_at=datetime.fromtimestamp(event.created, tz=UTC),
        )

    def _already_current(self, update: SubscriptionUpdate) -> bool:
        store = WorkspaceStore(self.tenant_root / update.tenant_id / "workspace")
        if not store.path.exists():
            return False
        workspace = store.load()
        return (
            workspace.plan is update.plan
            and workspace.status is update.status
            and workspace.cycle_anchor_day == update.cycle_anchor_day
        )

    def _apply(self, update: SubscriptionUpdate) -> SubscriptionApplyResult | None:
        try:
            return self.authority.apply(update)
        except SubscriptionAuthorityError as exc:
            message = str(exc)
            if (
                "Stale subscription event" in message
                or "Ambiguous subscription events" in message
            ) and self._already_current(update):
                return None
            raise StripeBillingError("Stripe subscription state could not be projected.") from exc

    def handle(self, event: StripeWebhookEvent) -> StripeWebhookResult:
        if event.type not in self._SUBSCRIPTION_EVENTS:
            return StripeWebhookResult(False, False, reason="event type ignored")
        try:
            event_subscription = StripeSubscription.model_validate(event.data.object)
        except ValidationError as exc:
            raise StripeBillingError("Stripe subscription event payload is invalid.") from exc

        if event.type == "customer.subscription.deleted":
            tenant_id = self._tenant_id(event_subscription)
            binding = self.bindings.load(tenant_id)
            if binding is None or binding.subscription_id != event_subscription.id:
                return StripeWebhookResult(
                    True,
                    False,
                    tenant_id=tenant_id,
                    reason="deleted subscription is not the current tenant binding",
                )
            current = event_subscription.model_copy(update={"status": "canceled"})
        else:
            current = self.client.retrieve_subscription(event_subscription.id)

        update = self._update(event=event, subscription=current)
        result = self._apply(update)
        self.bindings.save(
            StripeTenantBinding(
                tenant_id=update.tenant_id,
                customer_id=current.customer,
                subscription_id=current.id,
                updated_at=datetime.now(UTC),
            )
        )
        self.checkout_reservations.clear(update.tenant_id)
        return StripeWebhookResult(
            True,
            result.applied if result is not None else False,
            tenant_id=update.tenant_id,
            reason="subscription state reconciled",
        )
