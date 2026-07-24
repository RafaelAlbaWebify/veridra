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


class SessionStatus(StrEnum):
    active = "active"
    revoked = "revoked"


class TenantRole(StrEnum):
    owner = "owner"
    administrator = "administrator"
    analyst = "analyst"
    sales = "sales"
    viewer = "viewer"


class TenantCapability(StrEnum):
    manage_tenant = "manage_tenant"
    manage_memberships = "manage_memberships"
    manage_projects = "manage_projects"
    run_assessments = "run_assessments"
    manage_reports = "manage_reports"
    manage_leads = "manage_leads"
    manage_monitoring = "manage_monitoring"
    manage_tasks = "manage_tasks"
    view_data = "view_data"


TENANT_ROLE_CAPABILITIES: dict[TenantRole, frozenset[TenantCapability]] = {
    TenantRole.owner: frozenset(TenantCapability),
    TenantRole.administrator: frozenset(TenantCapability),
    TenantRole.analyst: frozenset(
        {
            TenantCapability.manage_projects,
            TenantCapability.run_assessments,
            TenantCapability.manage_reports,
            TenantCapability.manage_monitoring,
            TenantCapability.manage_tasks,
            TenantCapability.view_data,
        }
    ),
    TenantRole.sales: frozenset(
        {
            TenantCapability.manage_leads,
            TenantCapability.manage_reports,
            TenantCapability.view_data,
        }
    ),
    TenantRole.viewer: frozenset({TenantCapability.view_data}),
}


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


class AuthSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=24, max_length=128)
    user_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    status: SessionStatus = SessionStatus.active
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


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


def require_tenant_capability(
    identity: RequestIdentity,
    capability: TenantCapability,
) -> None:
    if capability not in TENANT_ROLE_CAPABILITIES[identity.membership_role]:
        raise IdentityBoundaryError(
            f"Tenant role {identity.membership_role.value} lacks {capability.value}."
        )


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


def build_request_identity(
    *,
    user: AuthenticatedUser,
    tenant: Tenant,
    membership: TenantMembership,
    session: AuthSession,
    now: datetime | None = None,
) -> RequestIdentity:
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if user.status != AccountStatus.active:
        raise IdentityBoundaryError("Authenticated user account is not active.")
    if user.email_verified_at is None:
        raise IdentityBoundaryError("Authenticated user email is not verified.")
    if tenant.status != TenantStatus.active:
        raise IdentityBoundaryError("Tenant is not active.")
    if membership.user_id != user.id or membership.tenant_id != tenant.id:
        raise IdentityBoundaryError("Membership does not match the authenticated user and tenant.")
    if not membership.active:
        raise IdentityBoundaryError("Tenant membership is inactive.")
    if session.user_id != user.id:
        raise IdentityBoundaryError("Session does not belong to the authenticated user.")
    if session.status != SessionStatus.active or session.revoked_at is not None:
        raise IdentityBoundaryError("Session has been revoked.")
    if session.expires_at <= checked_at:
        raise IdentityBoundaryError("Session has expired.")
    if session.issued_at > checked_at:
        raise IdentityBoundaryError("Session issue time is in the future.")
    return RequestIdentity(
        user_id=user.id,
        tenant_id=tenant.id,
        membership_role=membership.role,
        session_id=session.id,
        authenticated_at=session.issued_at,
    )
