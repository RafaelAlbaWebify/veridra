from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class IdentityBoundaryError(RuntimeError):
    pass


class TenantStatus(StrEnum):
    active = "active"
    suspended = "suspended"


class AccountStatus(StrEnum):
    pending = "pending"
    active = "active"
    disabled = "disabled"


class TenantRole(StrEnum):
    owner = "owner"
    administrator = "administrator"
    analyst = "analyst"
    sales = "sales"
    viewer = "viewer"


class Tenant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[0-9a-f]{24}$")
    slug: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_name: str = Field(min_length=1, max_length=160)
    status: TenantStatus = TenantStatus.active
    created_at: datetime

    @classmethod
    def build(
        cls,
        *,
        slug: str,
        display_name: str,
        now: datetime | None = None,
    ) -> Tenant:
        normalized_slug = slug.strip().lower()
        seed = json.dumps(
            {"slug": normalized_slug},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            id=hashlib.sha256(seed).hexdigest()[:24],
            slug=normalized_slug,
            display_name=display_name,
            created_at=(now or datetime.now(UTC)).astimezone(UTC),
        )


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[0-9a-f]{24}$")
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    status: AccountStatus = AccountStatus.pending
    email_verified_at: datetime | None = None
    created_at: datetime

    @classmethod
    def build(
        cls,
        *,
        email: str,
        display_name: str,
        now: datetime | None = None,
    ) -> AuthenticatedUser:
        normalized_email = email.strip().lower()
        seed = json.dumps(
            {"email": normalized_email},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            id=hashlib.sha256(seed).hexdigest()[:24],
            email=normalized_email,
            display_name=display_name,
            created_at=(now or datetime.now(UTC)).astimezone(UTC),
        )


class TenantMembership(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    user_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    role: TenantRole
    active: bool = True
    created_at: datetime


class RequestIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    user_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    membership_role: TenantRole
    session_id: str = Field(min_length=24, max_length=128)
    authenticated_at: datetime


class TenantObjectRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    object_type: str = Field(min_length=1, max_length=80)
    object_id: str = Field(min_length=1, max_length=160)


def require_tenant_scope(identity: RequestIdentity, target: TenantObjectRef) -> None:
    if identity.tenant_id != target.tenant_id:
        raise IdentityBoundaryError("Cross-tenant object access is forbidden.")


def require_active_membership(
    identity: RequestIdentity,
    membership: TenantMembership,
) -> None:
    if membership.user_id != identity.user_id or membership.tenant_id != identity.tenant_id:
        raise IdentityBoundaryError("Request identity does not match this tenant membership.")
    if not membership.active:
        raise IdentityBoundaryError("Tenant membership is inactive.")
    if membership.role != identity.membership_role:
        raise IdentityBoundaryError("Request role does not match the current membership.")
