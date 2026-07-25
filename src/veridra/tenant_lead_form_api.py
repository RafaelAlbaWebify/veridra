from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .identity_tenancy import RequestIdentity, TenantCapability, TenantObjectRef
from .lead_store import LeadFormConfig
from .request_security import require_request_capability
from .tenant_lead_form_store import TenantLeadFormStore, TenantLeadFormStoreError

router = APIRouter(prefix="/api/tenant/lead-forms", tags=["tenant-lead-forms"])
LeadFormReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
LeadFormManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_leads)),
]


def _store(request: Request) -> TenantLeadFormStore:
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    return TenantLeadFormStore(configured)


def _target(identity: RequestIdentity, form_id: str) -> TenantObjectRef:
    return TenantObjectRef(
        tenant_id=identity.tenant_id,
        object_type="lead-form",
        object_id=form_id,
    )


@router.get("")
def list_lead_forms(
    request: Request,
    identity: LeadFormReader,
) -> list[dict[str, object]]:
    return [
        {"id": form_id, **form.model_dump(mode="json")}
        for form_id, form in _store(request).list(identity)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_lead_form(
    payload: LeadFormConfig,
    request: Request,
    identity: LeadFormManager,
) -> dict[str, str]:
    form_id = _store(request).save(identity, payload)
    return {"id": form_id}


@router.get("/{form_id}", response_model=LeadFormConfig)
def get_lead_form(
    form_id: str,
    request: Request,
    identity: LeadFormReader,
) -> LeadFormConfig:
    try:
        return _store(request).load(identity, _target(identity, form_id))
    except TenantLeadFormStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead form not found.",
        ) from exc


@router.put("/{form_id}", response_model=LeadFormConfig)
def replace_lead_form(
    form_id: str,
    payload: LeadFormConfig,
    request: Request,
    identity: LeadFormManager,
) -> LeadFormConfig:
    try:
        target = _target(identity, form_id)
        _store(request).replace(identity, target, payload)
        return _store(request).load(identity, target)
    except TenantLeadFormStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead form not found.",
        ) from exc


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead_form(
    form_id: str,
    request: Request,
    identity: LeadFormManager,
) -> None:
    try:
        _store(request).delete(identity, _target(identity, form_id))
    except TenantLeadFormStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead form not found.",
        ) from exc
