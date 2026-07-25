from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from .identity_tenancy import RequestIdentity, TenantCapability
from .profile_store import ProfileEntry
from .report_profiles import ReportProfile
from .request_security import require_request_capability
from .tenant_profile_store import TenantProfileStore, TenantProfileStoreError

router = APIRouter(prefix="/api/tenant/report-profiles", tags=["tenant-report-profiles"])
ProfileReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
ProfileManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_reports)),
]


class ProfileSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    organisation_name: str
    client_name: str | None
    consultant_name: str | None

    @classmethod
    def from_entry(cls, entry: ProfileEntry) -> ProfileSummary:
        return cls(
            id=entry.id,
            organisation_name=entry.organisation_name,
            client_name=entry.client_name,
            consultant_name=entry.consultant_name,
        )


def _root(request: Request) -> Path | None:
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    return configured if isinstance(configured, Path) else None


def _store(request: Request) -> TenantProfileStore:
    return TenantProfileStore(_root(request))


@router.get("", response_model=list[ProfileSummary])
def list_profiles(request: Request, identity: ProfileReader) -> list[ProfileSummary]:
    return [ProfileSummary.from_entry(item) for item in _store(request).list(identity)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(
    profile: ReportProfile,
    request: Request,
    identity: ProfileManager,
) -> dict[str, str]:
    return {"id": _store(request).save(identity, profile)}


@router.get("/{profile_id}", response_model=ReportProfile)
def get_profile(
    profile_id: str,
    request: Request,
    identity: ProfileReader,
) -> ReportProfile:
    try:
        return _store(request).load(identity, TenantProfileStore.ref(identity, profile_id))
    except TenantProfileStoreError as exc:
        raise HTTPException(status_code=404, detail="Report profile not found.") from exc


@router.put("/{profile_id}", response_model=ReportProfile)
def replace_profile(
    profile_id: str,
    profile: ReportProfile,
    request: Request,
    identity: ProfileManager,
) -> ReportProfile:
    try:
        replacement_id = _store(request).replace(
            identity,
            TenantProfileStore.ref(identity, profile_id),
            profile,
        )
        return _store(request).load(
            identity,
            TenantProfileStore.ref(identity, replacement_id),
        )
    except TenantProfileStoreError as exc:
        raise HTTPException(status_code=404, detail="Report profile not found.") from exc


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: str,
    request: Request,
    identity: ProfileManager,
) -> None:
    try:
        _store(request).delete(identity, TenantProfileStore.ref(identity, profile_id))
    except TenantProfileStoreError as exc:
        raise HTTPException(status_code=404, detail="Report profile not found.") from exc
