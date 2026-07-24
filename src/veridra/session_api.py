from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict

from .identity_tenancy import RequestIdentity, TenantRole
from .request_security import require_request_identity
from .session_lifecycle import SessionLifecycleService
from .sqlite_identity_store import SQLiteIdentityRecordStore

SESSION_COOKIE_NAME = "veridra_session"
SESSION_LIFETIME = timedelta(hours=8)
AuthenticatedIdentity = Annotated[RequestIdentity, Depends(require_request_identity)]

router = APIRouter(prefix="/api/session", tags=["session"])


class CurrentSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str
    tenant_id: str
    role: TenantRole
    session_id: str
    authenticated_at: datetime


def set_session_cookie(
    response: Response,
    credential: str,
    *,
    max_age: int,
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=credential,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _identity_store(request: Request) -> SQLiteIdentityRecordStore:
    store = getattr(request.app.state, "veridra_identity_store", None)
    if not isinstance(store, SQLiteIdentityRecordStore):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity service is not configured.",
        )
    return store


@router.get("/current", response_model=CurrentSession)
def current_session(identity: AuthenticatedIdentity) -> CurrentSession:
    return CurrentSession(
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        role=identity.membership_role,
        session_id=identity.session_id,
        authenticated_at=identity.authenticated_at,
    )


@router.post("/rotate", response_model=CurrentSession)
def rotate_session(
    request: Request,
    response: Response,
    identity: AuthenticatedIdentity,
) -> CurrentSession:
    replacement = SessionLifecycleService(_identity_store(request)).rotate(
        current_session_id=identity.session_id,
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        lifetime=SESSION_LIFETIME,
    )
    set_session_cookie(
        response,
        replacement.credential,
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return CurrentSession(
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        role=identity.membership_role,
        session_id=replacement.session.id,
        authenticated_at=replacement.session.issued_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    identity: AuthenticatedIdentity,
) -> None:
    store = _identity_store(request)
    store.revoke_session(identity.session_id, revoked_at=datetime.now(UTC))
    clear_session_cookie(response)
