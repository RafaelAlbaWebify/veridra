from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .assessment_project_conversion_api import (
    AssessmentProjectConversion,
    AssessmentProjectCreated,
    convert_assessment,
)
from .customer_lifecycle import upsert_customer_from_lead
from .history import HistoryError, HistoryStore
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .lead_activity import LeadActivityError, LeadActivityType, TenantLeadActivityStore
from .lead_project_link_store import (
    LeadProjectLink,
    LeadProjectLinkError,
    LeadProjectLinkStore,
)
from .lead_store import AuditLead, LeadStatus
from .request_security import require_request_capability
from .tenant_customer_store import TenantCustomerStore, TenantCustomerStoreError
from .tenant_lead_form_store import TenantLeadFormStore, TenantLeadFormStoreError
from .tenant_lead_store import TenantLeadStore, TenantLeadStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

LeadConverter = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_leads)),
]


class LeadProjectConversion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_name: str = Field(min_length=1, max_length=120)
    client_label: str | None = Field(default=None, max_length=120)


class LeadProjectCreated(AssessmentProjectCreated):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lead_id: str
    existing: bool = False


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _base_root(request: Request) -> Path:
    return _root(request) or Path.home() / ".veridra" / "tenants"


def _links(request: Request, identity: RequestIdentity) -> LeadProjectLinkStore:
    return LeadProjectLinkStore(_base_root(request) / identity.tenant_id / "lead-project-links")


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail="Lead conversion source not found.")


def _won_lead(lead: AuditLead) -> AuditLead:
    return lead.model_copy(
        update={
            "status": LeadStatus.won,
            "won_at": lead.won_at or datetime.now(UTC),
            "lost_at": None,
            "loss_reason": "",
        }
    )


def _ensure_customer(
    request: Request,
    identity: RequestIdentity,
    *,
    lead_id: str,
    lead: AuditLead,
    project_id: str,
) -> None:
    try:
        upsert_customer_from_lead(
            TenantCustomerStore(_root(request)),
            identity,
            lead_id=lead_id,
            lead=lead,
            project_id=project_id,
        )
    except TenantCustomerStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail="Customer onboarding record could not be created.",
        ) from exc


def convert_lead_to_project(
    lead_id: str,
    payload: LeadProjectConversion,
    request: Request,
    identity: RequestIdentity,
) -> LeadProjectCreated:
    try:
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc

    root = _root(request)
    leads = TenantLeadStore(root)
    projects = TenantProjectStore(root)
    links = _links(request, identity)
    activity = TenantLeadActivityStore(_base_root(request))
    try:
        lead = leads.load(identity, leads.ref(identity, lead_id))
        existing = links.load(lead_id)
    except (TenantLeadStoreError, LeadProjectLinkError) as exc:
        raise _not_found(exc) from exc

    won_lead = _won_lead(lead)
    if existing is not None:
        try:
            projects.load(identity, projects.ref(identity, existing.project_id))
            if lead != won_lead:
                leads.replace(identity, leads.ref(identity, lead_id), won_lead)
            _ensure_customer(
                request,
                identity,
                lead_id=lead_id,
                lead=won_lead,
                project_id=existing.project_id,
            )
        except TenantProjectStoreError as exc:
            raise _not_found(exc) from exc
        return LeadProjectCreated(
            lead_id=lead_id,
            project_id=existing.project_id,
            assessment_id=existing.assessment_id,
            existing=True,
        )

    try:
        assessment = HistoryStore().load(lead.assessment_id)
        if str(assessment.target) != str(lead.website):
            raise HistoryError("Lead assessment target does not match the lead website.")
        forms = TenantLeadFormStore(root)
        form = forms.load(identity, forms.ref(identity, lead.form_id))
    except (HistoryError, TenantLeadFormStoreError) as exc:
        raise _not_found(exc) from exc

    created = convert_assessment(
        AssessmentProjectConversion(
            assessment=assessment,
            project_name=payload.project_name,
            client_label=payload.client_label,
            profile_id=form.profile_id,
        ),
        request,
        identity,
    )
    try:
        links.save(
            LeadProjectLink(
                lead_id=lead_id,
                project_id=created.project_id,
                assessment_id=created.assessment_id,
            )
        )
        leads.replace(identity, leads.ref(identity, lead_id), won_lead)
        activity.append(
            identity,
            lead_id,
            LeadActivityType.project_converted,
            "Lead converted to client project",
            metadata={"project_id": created.project_id},
        )
        _ensure_customer(
            request,
            identity,
            lead_id=lead_id,
            lead=won_lead,
            project_id=created.project_id,
        )
    except (LeadProjectLinkError, TenantLeadStoreError, LeadActivityError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Lead conversion could not be completed.",
        ) from exc
    return LeadProjectCreated(
        lead_id=lead_id,
        project_id=created.project_id,
        assessment_id=created.assessment_id,
    )


router = APIRouter(tags=["lead-project-conversion"])


@router.post(
    "/api/tenant/leads/{lead_id}/convert-project",
    response_model=LeadProjectCreated,
    status_code=status.HTTP_201_CREATED,
)
def convert_tenant_lead_to_project(
    lead_id: str,
    payload: LeadProjectConversion,
    request: Request,
    identity: LeadConverter,
) -> LeadProjectCreated:
    return convert_lead_to_project(lead_id, payload, request, identity)
