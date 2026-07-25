from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .identity_tenancy import RequestIdentity, TenantCapability, TenantRole
from .request_security import require_request_capability
from .tenant_invitations import SQLiteTenantInvitationService, TenantInvitationError

router = APIRouter(prefix="/api/invitations", tags=["invitations"])
MembershipManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_memberships)),
]


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: TenantRole


class InvitationCreateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str
    email: EmailStr
    role: TenantRole
    expires_at: datetime


class InvitationAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: str = Field(min_length=32, max_length=512)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=1024)


class InvitationAcceptResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str
    tenant_id: str
    role: TenantRole


def _service(request: Request) -> SQLiteTenantInvitationService:
    store = getattr(request.app.state, "veridra_identity_store", None)
    database = getattr(store, "database", None)
    if not isinstance(database, Path):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invitation service is not configured.",
        )
    return SQLiteTenantInvitationService(database)


@router.post("", response_model=InvitationCreateResponse, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreateRequest,
    request: Request,
    identity: MembershipManager,
) -> InvitationCreateResponse:
    try:
        issued = _service(request).issue(
            tenant_id=identity.tenant_id,
            created_by_user_id=identity.user_id,
            email=str(payload.email),
            role=payload.role,
        )
    except TenantInvitationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return InvitationCreateResponse(
        token=issued.token,
        email=issued.email,
        role=issued.role,
        expires_at=issued.expires_at,
    )


@router.post("/accept", response_model=InvitationAcceptResponse)
def accept_invitation(
    payload: InvitationAcceptRequest,
    request: Request,
) -> InvitationAcceptResponse:
    try:
        accepted = _service(request).accept(
            token=payload.token,
            display_name=payload.display_name,
            password=payload.password,
            now=datetime.now(UTC),
        )
    except TenantInvitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is invalid, expired, or already used.",
        ) from exc
    return InvitationAcceptResponse(
        user_id=accepted.user_id,
        tenant_id=accepted.tenant_id,
        role=accepted.role,
    )
