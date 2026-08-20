from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .password_recovery import PasswordRecoveryError, SQLitePasswordRecoveryService
from .password_recovery_throttle import SQLitePasswordRecoveryThrottle

router = APIRouter(prefix="/api/auth/password-recovery", tags=["authentication"])


@dataclass(frozen=True)
class PasswordResetDelivery:
    email: str
    token: str
    expires_at: datetime


class PasswordResetDeliveryAdapter(Protocol):
    def __call__(self, delivery: PasswordResetDelivery) -> None: ...


class PasswordRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=512)
    new_password: str = Field(min_length=12, max_length=1024)


def _database(request: Request) -> Path:
    database = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(database, Path):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password recovery is not configured.",
        )
    return database


def _service(request: Request) -> SQLitePasswordRecoveryService:
    return SQLitePasswordRecoveryService(_database(request))


def _throttle(request: Request) -> SQLitePasswordRecoveryThrottle:
    configured = getattr(request.app.state, "veridra_password_recovery_throttle", None)
    if isinstance(configured, SQLitePasswordRecoveryThrottle):
        return configured
    return SQLitePasswordRecoveryThrottle(_database(request))


def _delivery_adapter(request: Request) -> Callable[[PasswordResetDelivery], None]:
    adapter = getattr(request.app.state, "veridra_password_reset_delivery", None)
    if not callable(adapter):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password recovery delivery is not configured.",
        )
    return cast(Callable[[PasswordResetDelivery], None], adapter)


@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(payload: PasswordRecoveryRequest, request: Request) -> None:
    service = _service(request)
    adapter = _delivery_adapter(request)
    email = str(payload.email)
    if not _throttle(request).consume(email=email).allowed:
        return
    issued = service.issue(email=email)
    if issued is not None:
        adapter(
            PasswordResetDelivery(
                email=issued.email,
                token=issued.token,
                expires_at=issued.expires_at,
            )
        )


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: PasswordResetRequest, request: Request) -> None:
    try:
        _service(request).reset_password(
            token=payload.token,
            new_password=payload.new_password,
        )
    except PasswordRecoveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password-reset token is invalid.",
        ) from exc
