from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .identity_tenancy import RequestIdentity
from .request_security import require_request_identity
from .sqlite_identity_store import SQLiteIdentityRecordStore

SESSION_COOKIE_NAME = "veridra_session"
AuthenticatedIdentity = Annotated[RequestIdentity, Depends(require_request_identity)]

router = APIRouter(prefix="/api/session", tags=["session"])


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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    identity: AuthenticatedIdentity,
) -> None:
    store = _identity_store(request)
    store.revoke_session(identity.session_id, revoked_at=datetime.now(UTC))
    clear_session_cookie(response)
