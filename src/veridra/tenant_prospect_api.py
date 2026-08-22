from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .identity_tenancy import RequestIdentity, TenantCapability, TenantObjectRef
from .prospect import Prospect, ProspectStatus
from .request_security import require_request_capability
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError

router = APIRouter(prefix="/api/tenant/prospects", tags=["tenant-prospects"])
ProspectReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
ProspectManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_leads)),
]


def _store(request: Request) -> TenantProspectStore:
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    return TenantProspectStore(configured)


def _target(identity: RequestIdentity, prospect_id: str) -> TenantObjectRef:
    return TenantObjectRef(
        tenant_id=identity.tenant_id,
        object_type="prospect",
        object_id=prospect_id,
    )


@router.get("")
def list_prospects(
    request: Request,
    identity: ProspectReader,
    status_filter: ProspectStatus | None = None,
) -> list[dict[str, object]]:
    return [
        {"id": prospect_id, **prospect.model_dump(mode="json")}
        for prospect_id, prospect in _store(request).list(identity, status=status_filter)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_prospect(
    payload: Prospect,
    request: Request,
    identity: ProspectManager,
) -> dict[str, str]:
    prospect_id = _store(request).save(identity, payload)
    return {"id": prospect_id}


@router.get("/{prospect_id}", response_model=Prospect)
def get_prospect(
    prospect_id: str,
    request: Request,
    identity: ProspectReader,
) -> Prospect:
    try:
        return _store(request).load(identity, _target(identity, prospect_id))
    except TenantProspectStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect not found.",
        ) from exc


@router.put("/{prospect_id}", response_model=Prospect)
def replace_prospect(
    prospect_id: str,
    payload: Prospect,
    request: Request,
    identity: ProspectManager,
) -> Prospect:
    try:
        target = _target(identity, prospect_id)
        _store(request).replace(identity, target, payload)
        return _store(request).load(identity, target)
    except TenantProspectStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect not found.",
        ) from exc


@router.delete("/{prospect_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prospect(
    prospect_id: str,
    request: Request,
    identity: ProspectManager,
) -> None:
    try:
        _store(request).delete(identity, _target(identity, prospect_id))
    except TenantProspectStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect not found.",
        ) from exc
