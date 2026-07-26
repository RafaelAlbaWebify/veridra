from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .identity_tenancy import RequestIdentity
from .login_throttle import SQLiteLoginThrottle
from .password_auth import SQLitePasswordAuthenticator
from .request_security import require_request_identity
from .session_api import clear_session_cookie, set_session_cookie
from .session_lifecycle import SessionLifecycleService
from .sqlite_identity_store import SQLiteIdentityRecordStore

router = APIRouter(prefix="/api/auth", tags=["authentication"])
AuthenticatedIdentity = Annotated[RequestIdentity, Depends(require_request_identity)]


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


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


def _services(
    request: Request,
) -> tuple[SQLitePasswordAuthenticator, SessionLifecycleService, SQLiteLoginThrottle]:
    authenticator = getattr(request.app.state, "veridra_password_authenticator", None)
    identity_store = getattr(request.app.state, "veridra_identity_store", None)
    login_throttle = getattr(request.app.state, "veridra_login_throttle", None)
    if (
        not isinstance(authenticator, SQLitePasswordAuthenticator)
        or not isinstance(identity_store, SQLiteIdentityRecordStore)
        or not isinstance(login_throttle, SQLiteLoginThrottle)
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )
    return authenticator, SessionLifecycleService(identity_store), login_throttle


def _raise_locked(retry_after_seconds: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts. Try again later.",
        headers={"Retry-After": str(retry_after_seconds)},
    )


@router.post("/login", response_model=PasswordLoginResponse)
def login(
    payload: PasswordLoginRequest,
    request: Request,
    response: Response,
) -> PasswordLoginResponse:
    authenticator, lifecycle, login_throttle = _services(request)
    email = str(payload.email)
    now = datetime.now(UTC)
    decision = login_throttle.check(email=email, tenant_slug=payload.tenant_slug, now=now)
    if not decision.allowed:
        _raise_locked(decision.retry_after_seconds)
    records = authenticator.authenticate(
        email=email,
        tenant_slug=payload.tenant_slug,
        password=payload.password,
    )
    if records is None:
        failure = login_throttle.record_failure(
            email=email,
            tenant_slug=payload.tenant_slug,
            now=now,
        )
        if not failure.allowed:
            _raise_locked(failure.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login credentials.",
        )
    login_throttle.clear(email=email, tenant_slug=payload.tenant_slug)
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


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    identity: AuthenticatedIdentity,
) -> None:
    authenticator, _, _ = _services(request)
    changed = authenticator.change_password_and_revoke_sessions(
        user_id=identity.user_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        changed_at=datetime.now(UTC),
    )
    if not changed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is invalid.",
        )
    clear_session_cookie(response)
