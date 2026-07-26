from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .existing_user_invitations import SQLiteExistingUserInvitationService
from .identity_tenancy import RequestIdentity, TenantCapability, TenantRole
from .request_security import require_request_capability, require_request_identity
from .tenant_invitations import TenantInvitationError

router = APIRouter(prefix="/api/invitations", tags=["invitations"])
MembershipManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_memberships)),
]
AuthenticatedIdentity = Annotated[
    RequestIdentity,
    Depends(require_request_identity),
]


class ExistingInvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: TenantRole


class ExistingInvitationCreateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str
    email: EmailStr
    role: TenantRole
    expires_at: datetime


class ExistingInvitationAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: str = Field(min_length=32, max_length=512)


class ExistingInvitationAcceptResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str
    tenant_id: str
    role: TenantRole


def _service(request: Request) -> SQLiteExistingUserInvitationService:
    store = getattr(request.app.state, "veridra_identity_store", None)
    database = getattr(store, "database", None)
    if not isinstance(database, Path):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invitation service is not configured.",
        )
    return SQLiteExistingUserInvitationService(database)


@router.post(
    "/existing",
    response_model=ExistingInvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_existing_user_invitation(
    payload: ExistingInvitationCreateRequest,
    request: Request,
    identity: MembershipManager,
) -> ExistingInvitationCreateResponse:
    try:
        issued = _service(request).issue(
            tenant_id=identity.tenant_id,
            created_by_user_id=identity.user_id,
            email=str(payload.email),
            role=payload.role,
            now=datetime.now(UTC),
        )
    except TenantInvitationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ExistingInvitationCreateResponse(
        token=issued.token,
        email=issued.email,
        role=issued.role,
        expires_at=issued.expires_at,
    )


@router.post(
    "/accept-existing",
    response_model=ExistingInvitationAcceptResponse,
)
def accept_existing_user_invitation(
    payload: ExistingInvitationAcceptRequest,
    request: Request,
    identity: AuthenticatedIdentity,
) -> ExistingInvitationAcceptResponse:
    try:
        accepted = _service(request).accept(
            token=payload.token,
            user_id=identity.user_id,
            now=datetime.now(UTC),
        )
    except TenantInvitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is invalid, expired, used, or belongs to another account.",
        ) from exc
    return ExistingInvitationAcceptResponse(
        user_id=accepted.user_id,
        tenant_id=accepted.tenant_id,
        role=accepted.role,
    )
