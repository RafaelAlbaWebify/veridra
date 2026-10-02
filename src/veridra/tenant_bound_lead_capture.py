from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from .collector import CollectionError
from .core import UnsafeTargetError
from .crawl_profiles import anonymous_crawl_profile
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
from .report_profiles import ReportProfile
from .runtime_config import RuntimeConfig, RuntimeEnvironment
from .service import assess_url
from .tenant_assessment_usage import crawled_page_count
from .tenant_delivery_stores import TenantDeliveryStores
from .tenant_entitlements import (
    record_bound_tenant_reserved_usage,
    release_bound_tenant_usage_reservation,
    require_bound_tenant_feature,
    reserve_bound_tenant_usage,
)
from .tenant_lead_assessment_store import (
    TenantLeadAssessmentStore,
    TenantLeadAssessmentStoreError,
)
from .tenant_lead_form_store import TenantLeadFormStore, TenantLeadFormStoreError
from .tenant_lead_store import TenantLeadStore
from .tenant_profile_store import TenantProfileStore, TenantProfileStoreError
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import UsageKind

router = APIRouter(tags=["leads"])


def _binding(request: Request, form_id: str) -> LeadFormTenantBinding | None:
    configured_database = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(configured_database, Path):
        return None
    return SQLiteLeadFormTenantBindingStore(configured_database).resolve(form_id)


def _tenant_root(request: Request) -> Path | None:
    configured_root = getattr(request.app.state, "veridra_tenant_data_root", None)
    return configured_root if isinstance(configured_root, Path) else None


def _resolved_tenant_root(request: Request) -> Path:
    return TenantWorkspacePolicy(_tenant_root(request)).root


def _production_mode(request: Request) -> bool:
    config = getattr(request.app.state, "veridra_runtime_config", None)
    return (
        isinstance(config, RuntimeConfig)
        and config.environment is RuntimeEnvironment.production
    )


def _require_bound_in_production(
    request: Request,
    binding: LeadFormTenantBinding | None,
) -> None:
    if _production_mode(request) and binding is None:
        raise HTTPException(status_code=404, detail="Lead form not found.")


def _require_bound_form_feature(
    request: Request,
    binding: LeadFormTenantBinding | None,
) -> None:
    if binding is None:
        return
    require_bound_tenant_feature(
        _resolved_tenant_root(request),
        binding.tenant_id,
        "embedded_lead_forms",
    )


def _resolve_form(request: Request, form_id: str) -> LeadFormConfig:
    binding = _binding(request, form_id)
    _require_bound_in_production(request, binding)
    if binding is None:
        return _load_form(form_id)
    try:
        return TenantLeadFormStore(_tenant_root(request)).load_public(
            tenant_id=binding.tenant_id,
            form_id=form_id,
        )
    except TenantLeadFormStoreError as exc:
        if _production_mode(request):
            raise HTTPException(status_code=404, detail="Lead form not found.") from exc
        return _load_form(form_id)


def _resolve_brand_profile(
    request: Request,
    binding: LeadFormTenantBinding | None,
    config: LeadFormConfig,
) -> ReportProfile | None:
    if binding is None or config.profile_id is None:
        return None
    try:
        return TenantProfileStore(_tenant_root(request)).load_public(
            tenant_id=binding.tenant_id,
            profile_id=config.profile_id,
        )
    except TenantProfileStoreError:
        return None


def _branded_config(
    config: LeadFormConfig,
    profile: ReportProfile | None,
) -> LeadFormConfig:
    if profile is None:
        return config
    return config.model_copy(update={"organisation_label": profile.organisation_name})


def _public_brand(
    profile: ReportProfile | None,
) -> tuple[str, str | None]:
    if profile is None:
        return "#22272d", None
    return profile.accent_colour, profile.logo_data_uri


def _save_lead(request: Request, lead: AuditLead) -> str:
    binding = _binding(request, lead.form_id)
    _require_bound_in_production(request, binding)
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
    binding = _binding(request, form_id)
    _require_bound_in_production(request, binding)
    _require_bound_form_feature(request, binding)
    config = _resolve_form(request, form_id)
    _enforce_origin(request, config)
    profile = _resolve_brand_profile(request, binding, config)
    branded = _branded_config(config, profile)
    accent_colour, logo_data_uri = _public_brand(profile)
    return _page(
        config.heading,
        _public_form(form_id, branded),
        public=True,
        accent_colour=accent_colour,
        logo_data_uri=logo_data_uri,
    )


@router.post("/embed/audit/{form_id}", response_class=HTMLResponse)
async def submit_tenant_bound_embedded_audit(form_id: str, request: Request) -> str:
    binding = _binding(request, form_id)
    _require_bound_in_production(request, binding)
    _require_bound_form_feature(request, binding)
    config = _resolve_form(request, form_id)
    _enforce_origin(request, config)
    profile = _resolve_brand_profile(request, binding, config)
    branded = _branded_config(config, profile)
    _enforce_rate_limit(request, form_id)
    body = await request.body()
    if _single(body, "consent") != "yes":
        raise HTTPException(status_code=400, detail="Explicit consent is required.")

    audit_reservation = ""
    lead_reservation = ""
    page_reservation = ""
    root: Path | None = None
    if binding is not None:
        root = _resolved_tenant_root(request)
        audit_reservation = reserve_bound_tenant_usage(
            root,
            binding.tenant_id,
            UsageKind.audit,
        )
        try:
            lead_reservation = reserve_bound_tenant_usage(
                root,
                binding.tenant_id,
                UsageKind.lead_submission,
            )
            page_reservation = reserve_bound_tenant_usage(
                root,
                binding.tenant_id,
                UsageKind.crawled_page,
                quantity=anonymous_crawl_profile().limits.max_pages,
            )
        except Exception:
            release_bound_tenant_usage_reservation(
                root,
                binding.tenant_id,
                audit_reservation,
            )
            release_bound_tenant_usage_reservation(
                root,
                binding.tenant_id,
                lead_reservation,
            )
            raise

    try:
        assessment = assess_url(_single(body, "website"))
    except (UnsafeTargetError, CollectionError) as exc:
        if binding is not None and root is not None:
            for reservation_id in (
                audit_reservation,
                lead_reservation,
                page_reservation,
            ):
                release_bound_tenant_usage_reservation(
                    root,
                    binding.tenant_id,
                    reservation_id,
                )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        assessment_id = (
            TenantLeadAssessmentStore(root).save_bound_public_capture(
                tenant_id=binding.tenant_id,
                assessment=assessment,
            )
            if binding is not None and root is not None
            else _history().save(assessment)
        )
    except (TenantLeadAssessmentStoreError, OSError) as exc:
        if binding is not None and root is not None:
            for reservation_id in (
                audit_reservation,
                lead_reservation,
                page_reservation,
            ):
                release_bound_tenant_usage_reservation(
                    root,
                    binding.tenant_id,
                    reservation_id,
                )
        raise HTTPException(
            status_code=500,
            detail="Lead assessment could not be persisted.",
        ) from exc

    if binding is not None and root is not None:
        record_bound_tenant_reserved_usage(
            root,
            binding.tenant_id,
            audit_reservation,
            UsageKind.audit,
            related_id=assessment_id,
            note="Embedded tenant lead audit",
        )
        record_bound_tenant_reserved_usage(
            root,
            binding.tenant_id,
            page_reservation,
            UsageKind.crawled_page,
            quantity=crawled_page_count(assessment),
            related_id=assessment_id,
            note="Embedded tenant lead crawl pages",
        )

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
        if binding is not None and root is not None:
            release_bound_tenant_usage_reservation(
                root,
                binding.tenant_id,
                lead_reservation,
            )
        raise HTTPException(status_code=400, detail="Invalid lead submission.") from exc

    try:
        lead_id = _save_lead(request, lead)
    except Exception:
        if binding is not None and root is not None:
            release_bound_tenant_usage_reservation(
                root,
                binding.tenant_id,
                lead_reservation,
            )
        raise

    if binding is not None and root is not None:
        record_bound_tenant_reserved_usage(
            root,
            binding.tenant_id,
            lead_reservation,
            UsageKind.lead_submission,
            related_id=lead_id,
            note="Embedded tenant lead submission",
        )
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
        f"<section><p class='muted'>{html.escape(branded.organisation_label)}</p>"
        "<h1>Your website assessment is ready</h1>"
        f"<p>Thank you, {html.escape(lead.name)}. "
        "The bounded assessment completed successfully.</p>"
        f"<div class='metrics'>{metrics}</div>"
        "<p class='muted'>The organisation may contact you under the consent wording "
        "shown in the form. This result is not a penetration test.</p></section>"
    )
    accent_colour, logo_data_uri = _public_brand(profile)
    return _page(
        "Assessment complete",
        body_html,
        public=True,
        accent_colour=accent_colour,
        logo_data_uri=logo_data_uri,
    )
