from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from .collector import CollectionError
from .core import UnsafeTargetError
from .email_delivery import EmailAttemptStore, EmailDeliveryError, send_lead_notification
from .lead_delivery import LeadDeliveryStore, deliver_lead_webhook
from .lead_form_tenant_binding import (
    LeadFormTenantBinding,
    SQLiteLeadFormTenantBindingStore,
)
from .lead_store import AuditLead, LeadFormConfig, consent_timestamp
from .lead_web import (
    _enforce_origin,
    _enforce_rate_limit,
    _history,
    _leads,
    _load_form,
    _page,
    _public_form,
    _single,
)
from .service import assess_url
from .tenant_delivery_stores import TenantDeliveryStores
from .tenant_lead_form_store import TenantLeadFormStore, TenantLeadFormStoreError
from .tenant_lead_store import TenantLeadStore

router = APIRouter(tags=["leads"])


def _binding(request: Request, form_id: str) -> LeadFormTenantBinding | None:
    configured_database = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(configured_database, Path):
        return None
    return SQLiteLeadFormTenantBindingStore(configured_database).resolve(form_id)


def _tenant_root(request: Request) -> Path | None:
    configured_root = getattr(request.app.state, "veridra_tenant_data_root", None)
    return configured_root if isinstance(configured_root, Path) else None


def _resolve_form(request: Request, form_id: str) -> LeadFormConfig:
    binding = _binding(request, form_id)
    if binding is None:
        return _load_form(form_id)
    try:
        return TenantLeadFormStore(_tenant_root(request)).load_public(
            tenant_id=binding.tenant_id,
            form_id=form_id,
        )
    except TenantLeadFormStoreError:
        return _load_form(form_id)


def _save_lead(request: Request, lead: AuditLead) -> str:
    binding = _binding(request, lead.form_id)
    if binding is None:
        return _leads().save(lead)
    return TenantLeadStore(_tenant_root(request)).save_bound_public_capture(
        tenant_id=binding.tenant_id,
        lead=lead,
    )


def _attempt_stores(
    request: Request,
    form_id: str,
) -> tuple[LeadDeliveryStore | None, EmailAttemptStore | None]:
    binding = _binding(request, form_id)
    if binding is None:
        return None, None
    stores = TenantDeliveryStores(_tenant_root(request))
    return (
        stores.webhook_attempts(binding.tenant_id),
        stores.email_attempts(binding.tenant_id),
    )


@router.get("/embed/audit/{form_id}", response_class=HTMLResponse)
def tenant_bound_embedded_audit_form(form_id: str, request: Request) -> str:
    config = _resolve_form(request, form_id)
    _enforce_origin(request, config)
    return _page(config.heading, _public_form(form_id, config), public=True)


@router.post("/embed/audit/{form_id}", response_class=HTMLResponse)
async def submit_tenant_bound_embedded_audit(form_id: str, request: Request) -> str:
    config = _resolve_form(request, form_id)
    _enforce_origin(request, config)
    _enforce_rate_limit(request, form_id)
    body = await request.body()
    if _single(body, "consent") != "yes":
        raise HTTPException(status_code=400, detail="Explicit consent is required.")
    try:
        assessment = assess_url(_single(body, "website"))
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assessment_id = _history().save(assessment)
    try:
        lead = AuditLead(
            form_id=form_id,
            website=assessment.target,
            name=_single(body, "name"),
            email=_single(body, "email"),
            company=_single(body, "company") if config.collect_company else "",
            phone=_single(body, "phone") if config.collect_phone else "",
            consent_text=config.consent_text,
            consented_at=consent_timestamp(),
            assessment_id=assessment_id,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid lead submission.") from exc
    lead_id = _save_lead(request, lead)
    webhook_store, email_store = _attempt_stores(request, form_id)
    await deliver_lead_webhook(
        lead_id=lead_id,
        lead=lead,
        assessment=assessment,
        config=config,
        store=webhook_store,
    )
    try:
        send_lead_notification(
            lead_id=lead_id,
            lead=lead,
            assessment=assessment,
            recipient=(str(config.notification_email) if config.notification_email else None),
            store=email_store,
        )
    except EmailDeliveryError:
        pass
    metrics = "".join(
        f"<article class='metric'><span>{html.escape(key.title())}</span>"
        f"<strong>{value}</strong></article>"
        for key, value in assessment.summary.items()
    )
    body_html = (
        f"<section><p class='muted'>{html.escape(config.organisation_label)}</p>"
        "<h1>Your website assessment is ready</h1>"
        f"<p>Thank you, {html.escape(lead.name)}. "
        "The bounded assessment completed successfully.</p>"
        f"<div class='metrics'>{metrics}</div>"
        "<p class='muted'>The organisation may contact you under the consent wording "
        "shown in the form. This result is not a penetration test.</p></section>"
    )
    return _page("Assessment complete", body_html, public=True)
