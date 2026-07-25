from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from .collector import CollectionError
from .core import UnsafeTargetError
from .email_delivery import EmailDeliveryError, send_lead_notification
from .lead_delivery import deliver_lead_webhook
from .lead_form_tenant_binding import SQLiteLeadFormTenantBindingStore
from .lead_store import AuditLead, consent_timestamp
from .lead_web import (
    _enforce_origin,
    _enforce_rate_limit,
    _history,
    _leads,
    _load_form,
    _page,
    _single,
)
from .service import assess_url
from .tenant_lead_store import TenantLeadStore

router = APIRouter(tags=["leads"])


def _save_lead(request: Request, lead: AuditLead) -> str:
    configured_database = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(configured_database, Path):
        return _leads().save(lead)
    binding = SQLiteLeadFormTenantBindingStore(configured_database).resolve(lead.form_id)
    if binding is None:
        return _leads().save(lead)
    configured_root = getattr(request.app.state, "veridra_tenant_data_root", None)
    root = configured_root if isinstance(configured_root, Path) else None
    return TenantLeadStore(root).save_bound_public_capture(
        tenant_id=binding.tenant_id,
        lead=lead,
    )


@router.post("/embed/audit/{form_id}", response_class=HTMLResponse)
async def submit_tenant_bound_embedded_audit(form_id: str, request: Request) -> str:
    config = _load_form(form_id)
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
    await deliver_lead_webhook(
        lead_id=lead_id,
        lead=lead,
        assessment=assessment,
        config=config,
    )
    try:
        send_lead_notification(
            lead_id=lead_id,
            lead=lead,
            assessment=assessment,
            recipient=(str(config.notification_email) if config.notification_email else None),
        )
    except EmailDeliveryError:
        pass
    metrics = "".join(
        f"<article class='metric'><span>{key.title()}</span><strong>{value}</strong></article>"
        for key, value in assessment.summary.items()
    )
    body_html = (
        f"<section><p class='muted'>{config.organisation_label}</p>"
        "<h1>Your website assessment is ready</h1>"
        f"<p>Thank you, {lead.name}. The bounded assessment completed successfully.</p>"
        f"<div class='metrics'>{metrics}</div>"
        "<p class='muted'>The organisation may contact you under the consent wording "
        "shown in the form. This result is not a penetration test.</p></section>"
    )
    return _page("Assessment complete", body_html, public=True)
