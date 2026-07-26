from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .identity_tenancy import RequestIdentity, TenantCapability, TenantObjectRef
from .lead_store import AuditLead, LeadStatus
from .request_security import require_request_capability
from .tenant_delivery_stores import TenantDeliveryStores
from .tenant_lead_store import TenantLeadStore, TenantLeadStoreError

router = APIRouter(prefix="/api/tenant/leads", tags=["tenant-leads"])
LeadReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
LeadManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_leads)),
]


def _store(request: Request) -> TenantLeadStore:
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    return TenantLeadStore(configured)


def _delivery_stores(request: Request) -> TenantDeliveryStores:
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    root = configured if isinstance(configured, Path) else None
    return TenantDeliveryStores(root)


def _target(identity: RequestIdentity, lead_id: str) -> TenantObjectRef:
    return TenantObjectRef(
        tenant_id=identity.tenant_id,
        object_type="lead",
        object_id=lead_id,
    )


@router.get("")
def list_leads(
    request: Request,
    identity: LeadReader,
    status_filter: LeadStatus | None = None,
) -> list[dict[str, object]]:
    return [
        {"id": lead_id, **lead.model_dump(mode="json")}
        for lead_id, lead in _store(request).list(identity, status=status_filter)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: AuditLead,
    request: Request,
    identity: LeadManager,
) -> dict[str, str]:
    lead_id = _store(request).save(identity, payload)
    return {"id": lead_id}


@router.get("/{lead_id}", response_model=AuditLead)
def get_lead(
    lead_id: str,
    request: Request,
    identity: LeadReader,
) -> AuditLead:
    try:
        return _store(request).load(identity, _target(identity, lead_id))
    except TenantLeadStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found.",
        ) from exc


@router.get("/{lead_id}/delivery-attempts")
def list_delivery_attempts(
    lead_id: str,
    request: Request,
    identity: LeadReader,
) -> dict[str, list[dict[str, object]]]:
    try:
        _store(request).load(identity, _target(identity, lead_id))
    except TenantLeadStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found.",
        ) from exc
    stores = _delivery_stores(request)
    webhook_attempts = [
        {"id": attempt_id, **attempt.model_dump(mode="json")}
        for attempt_id, attempt in stores.webhook_attempts(identity.tenant_id).list_for_lead(
            lead_id
        )
    ]
    email_attempts = [
        {"id": attempt_id, **attempt.model_dump(mode="json")}
        for attempt_id, attempt in stores.email_attempts(identity.tenant_id).list_for_related(
            lead_id
        )
    ]
    return {"webhook": webhook_attempts, "email": email_attempts}


@router.put("/{lead_id}", response_model=AuditLead)
def replace_lead(
    lead_id: str,
    payload: AuditLead,
    request: Request,
    identity: LeadManager,
) -> AuditLead:
    try:
        target = _target(identity, lead_id)
        _store(request).replace(identity, target, payload)
        return _store(request).load(identity, target)
    except TenantLeadStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found.",
        ) from exc


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(
    lead_id: str,
    request: Request,
    identity: LeadManager,
) -> None:
    try:
        _store(request).delete(identity, _target(identity, lead_id))
    except TenantLeadStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found.",
        ) from exc
