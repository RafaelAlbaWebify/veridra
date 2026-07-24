from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .password_auth import SQLitePasswordAuthenticator
from .session_api import set_session_cookie
from .session_lifecycle import SessionLifecycleService
from .sqlite_identity_store import SQLiteIdentityRecordStore

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    tenant_slug: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    password: str = Field(min_length=1, max_length=1024)


class PasswordLoginResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str
    tenant_id: str
    role: str


def _services(
    request: Request,
) -> tuple[SQLitePasswordAuthenticator, SessionLifecycleService]:
    authenticator = getattr(request.app.state, "veridra_password_authenticator", None)
    identity_store = getattr(request.app.state, "veridra_identity_store", None)
    if not isinstance(authenticator, SQLitePasswordAuthenticator) or not isinstance(
        identity_store, SQLiteIdentityRecordStore
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )
    return authenticator, SessionLifecycleService(identity_store)


@router.post("/login", response_model=PasswordLoginResponse)
def login(
    payload: PasswordLoginRequest,
    request: Request,
    response: Response,
) -> PasswordLoginResponse:
    authenticator, lifecycle = _services(request)
    records = authenticator.authenticate(
        email=str(payload.email),
        tenant_slug=payload.tenant_slug,
        password=payload.password,
    )
    if records is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login credentials.",
        )
    lifetime = timedelta(hours=8)
    issued = lifecycle.issue(
        user_id=records.user.id,
        tenant_id=records.tenant.id,
        lifetime=lifetime,
    )
    set_session_cookie(response, issued.credential, max_age=int(lifetime.total_seconds()))
    return PasswordLoginResponse(
        user_id=records.user.id,
        tenant_id=records.tenant.id,
        role=records.membership.role.value,
    )
