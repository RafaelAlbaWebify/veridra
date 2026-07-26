from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import RequestIdentity, TenantCapability
from .lead_form_tenant_binding import (
    LeadFormTenantBindingError,
    SQLiteLeadFormTenantBindingStore,
)
from .lead_store import LeadFormStore, LeadStoreError
from .request_security import require_request_capability
from .tenant_lead_form_store import TenantLeadFormStore, TenantLeadFormStoreError

router = APIRouter(prefix="/api/tenant/lead-forms", tags=["tenant-lead-forms"])
LeadManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_leads)),
]


class LeadFormBindingResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    form_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")


def _store(request: Request) -> SQLiteLeadFormTenantBindingStore:
    database = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(database, Path):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant lead-form binding is not configured.",
        )
    return SQLiteLeadFormTenantBindingStore(database)


def _require_form(request: Request, identity: RequestIdentity, form_id: str) -> None:
    configured_root = getattr(request.app.state, "veridra_tenant_data_root", None)
    root = configured_root if isinstance(configured_root, Path) else None
    tenant_store = TenantLeadFormStore(root)
    try:
        tenant_store.load(identity, tenant_store.ref(identity, form_id))
        return
    except TenantLeadFormStoreError:
        pass
    try:
        LeadFormStore().load_form(form_id)
    except LeadStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead form not found.") from exc


@router.put("/{form_id}/binding", response_model=LeadFormBindingResponse)
def bind_form(
    form_id: str,
    request: Request,
    identity: LeadManager,
) -> LeadFormBindingResponse:
    _require_form(request, identity, form_id)
    try:
        binding = _store(request).bind(
            form_id=form_id,
            tenant_id=identity.tenant_id,
            created_by_user_id=identity.user_id,
        )
    except LeadFormTenantBindingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return LeadFormBindingResponse(form_id=binding.form_id, tenant_id=binding.tenant_id)


@router.get("/{form_id}/binding", response_model=LeadFormBindingResponse)
def get_binding(
    form_id: str,
    request: Request,
    identity: LeadManager,
) -> LeadFormBindingResponse:
    binding = _store(request).resolve(form_id)
    if binding is None or binding.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Lead form binding not found.")
    return LeadFormBindingResponse(form_id=binding.form_id, tenant_id=binding.tenant_id)


@router.delete("/{form_id}/binding", status_code=status.HTTP_204_NO_CONTENT)
def unbind_form(
    form_id: str,
    request: Request,
    identity: LeadManager,
) -> None:
    try:
        _store(request).unbind(form_id=form_id, tenant_id=identity.tenant_id)
    except LeadFormTenantBindingError as exc:
        raise HTTPException(status_code=404, detail="Lead form binding not found.") from exc
