# ruff: noqa: E501
from __future__ import annotations

import html
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .request_security import require_request_identity
from .runtime_billing import StripeBillingRuntime
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .stripe_billing import StripeBillingError
from .stripe_webhook_verification import verify_stripe_signature_with_secrets
from .workspace_policy import PlanName, WorkspaceStore

router = APIRouter(tags=["billing"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:860px;margin:40px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.plans{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.plan{border:1px solid #dfe3e8;border-radius:8px;padding:18px}button,.button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.muted{color:#68707a}.notice{border-left:4px solid #16794a;background:#f0faf5;padding:12px 14px}.cancelled{border-left-color:#68707a;background:#f4f6f8}@media(max-width:720px){.plans{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>",
        headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"},
    )


def _runtime(request: Request) -> StripeBillingRuntime:
    runtime = getattr(request.app.state, "veridra_stripe_billing", None)
    if not isinstance(runtime, StripeBillingRuntime):
        raise HTTPException(status_code=503, detail="Billing is not configured.")
    return runtime


def _identity(request: Request) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_tenant)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="Billing management is not permitted.") from exc
    return identity


def _same_origin(request: Request, runtime: StripeBillingRuntime) -> None:
    try:
        TrustedSameOriginPolicy(runtime.config.trusted_origin).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Billing request is not permitted.") from exc


def _tenant_root(request: Request) -> Path:
    root = getattr(request.app.state, "veridra_tenant_data_root", None)
    if not isinstance(root, Path):
        raise HTTPException(status_code=503, detail="Billing tenant storage is not configured.")
    return root


def _identity_database(request: Request) -> Path:
    store = getattr(request.app.state, "veridra_identity_store", None)
    database = getattr(store, "database", None)
    if not isinstance(database, Path):
        raise HTTPException(status_code=503, detail="Billing identity storage is not configured.")
    return database


def _user_email(request: Request, user_id: str) -> str:
    with sqlite3.connect(_identity_database(request)) as connection:
        row = connection.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or not isinstance(row[0], str) or not row[0]:
        raise HTTPException(status_code=503, detail="Billing account email is unavailable.")
    return row[0]


def _stripe_redirect(url: str, *, host: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username or parsed.password:
        raise StripeBillingError("Stripe returned an unexpected redirect destination.")
    return url


@router.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request, checkout: str = "") -> HTMLResponse:
    runtime = _runtime(request)
    identity = _identity(request)
    root = _tenant_root(request)
    workspace_store = WorkspaceStore(root / identity.tenant_id / "workspace")
    if not workspace_store.path.exists():
        raise HTTPException(status_code=404, detail="Tenant workspace was not found.")
    workspace = workspace_store.load()
    binding = runtime.adapter.bindings.load(identity.tenant_id)
    if binding is not None or checkout == "cancelled":
        try:
            runtime.adapter.checkout_reservations.clear(identity.tenant_id)
        except StripeBillingError as exc:
            raise HTTPException(status_code=503, detail="Billing state is unavailable.") from exc
    notice = ""
    if checkout == "success":
        notice = "<p class='notice'>Checkout completed. Stripe is reconciling the subscription; this page reflects only webhook-confirmed entitlement state.</p>"
    elif checkout == "cancelled":
        notice = "<p class='notice cancelled'>Checkout was cancelled. No plan change is assumed.</p>"

    status = html.escape(workspace.status.value.title())
    current = html.escape(workspace.plan.value.title())
    if binding is not None:
        action = "<form method='post' action='/billing/portal'><button type='submit'>Manage subscription in Stripe</button></form>"
        guidance = "Your Stripe subscription is already bound to this workspace. Use the Billing Portal for plan changes, payment methods or cancellation."
    else:
        cards = "".join(
            f"<article class='plan'><h2>{html.escape(plan.value.title())}</h2><form method='post' action='/billing/checkout/{plan.value}'><button type='submit'>Choose {html.escape(plan.value.title())}</button></form></article>"
            for plan in (PlanName.solo, PlanName.professional, PlanName.agency)
        )
        action = f"<div class='plans'>{cards}</div>"
        guidance = "Choose a paid plan to continue to Stripe-hosted Checkout. Veridra changes entitlements only after a verified Stripe subscription webhook is reconciled."

    body = f"<p><a href='/agency'>Agency home</a></p><section><h1>Billing</h1>{notice}<p><strong>Current Veridra plan:</strong> {current}<br><strong>Workspace status:</strong> {status}</p><p class='muted'>{html.escape(guidance)}</p>{action}</section>"
    return _page("Veridra billing", body)


@router.post("/billing/checkout/{plan}", response_model=None)
def start_checkout(plan: PlanName, request: Request) -> RedirectResponse:
    runtime = _runtime(request)
    identity = _identity(request)
    _same_origin(request, runtime)
    if plan is PlanName.free:
        raise HTTPException(status_code=400, detail="The free plan does not use Stripe Checkout.")
    if runtime.adapter.bindings.load(identity.tenant_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="An existing Stripe subscription must be managed through the Billing Portal.",
        )
    try:
        reservation = runtime.adapter.checkout_reservations.reserve(
            tenant_id=identity.tenant_id,
            plan=plan,
        )
    except StripeBillingError as exc:
        raise HTTPException(
            status_code=409,
            detail="Another Stripe Checkout is already in progress for this workspace.",
        ) from exc
    try:
        session = runtime.client.create_checkout(
            tenant_id=identity.tenant_id,
            customer_email=_user_email(request, identity.user_id),
            plan=plan,
            idempotency_key=reservation.idempotency_key,
        )
        destination = _stripe_redirect(session.url, host="checkout.stripe.com")
    except StripeBillingError as exc:
        raise HTTPException(status_code=502, detail="Stripe Checkout is unavailable.") from exc
    return RedirectResponse(destination, status_code=303)


@router.post("/billing/portal", response_model=None)
def open_billing_portal(request: Request) -> RedirectResponse:
    runtime = _runtime(request)
    identity = _identity(request)
    _same_origin(request, runtime)
    binding = runtime.adapter.bindings.load(identity.tenant_id)
    if binding is None:
        raise HTTPException(status_code=409, detail="No Stripe subscription is bound to this workspace.")
    try:
        session = runtime.client.create_portal(customer_id=binding.customer_id)
        destination = _stripe_redirect(session.url, host="billing.stripe.com")
    except StripeBillingError as exc:
        raise HTTPException(status_code=502, detail="Stripe Billing Portal is unavailable.") from exc
    return RedirectResponse(destination, status_code=303)


@router.post("/api/billing/stripe/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    runtime = _runtime(request)
    raw_body = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        verify_stripe_signature_with_secrets(
            raw_body,
            signature,
            runtime.webhook_secrets,
        )
        event = runtime.adapter.parse_event(raw_body)
    except StripeBillingError as exc:
        raise HTTPException(status_code=400, detail="Stripe webhook is invalid.") from exc
    try:
        result = runtime.adapter.handle(event)
    except StripeBillingError as exc:
        raise HTTPException(status_code=503, detail="Stripe webhook reconciliation failed.") from exc
    return JSONResponse(
        {
            "received": True,
            "handled": result.handled,
            "applied": result.applied,
        }
    )
