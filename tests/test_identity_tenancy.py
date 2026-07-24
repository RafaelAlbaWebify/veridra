from __future__ import annotations

from datetime import UTC, datetime

import pytest

from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    IdentityBoundaryError,
    RequestIdentity,
    Tenant,
    TenantMembership,
    TenantObjectRef,
    TenantRole,
    require_active_membership,
    require_tenant_scope,
)


NOW = datetime(2026, 7, 24, 7, 0, tzinfo=UTC)


def test_tenant_and_user_identifiers_are_stable_and_normalized() -> None:
    first_tenant = Tenant.build(slug=" Agency-One ", display_name="Agency One", now=NOW)
    second_tenant = Tenant.build(slug="agency-one", display_name="Renamed Agency", now=NOW)
    first_user = AuthenticatedUser.build(
        email="OWNER@EXAMPLE.COM",
        display_name="Owner",
        now=NOW,
    )
    second_user = AuthenticatedUser.build(
        email="owner@example.com",
        display_name="Renamed Owner",
        now=NOW,
    )

    assert first_tenant.id == second_tenant.id
    assert first_tenant.slug == "agency-one"
    assert first_user.id == second_user.id
    assert str(first_user.email) == "owner@example.com"
    assert first_user.status == AccountStatus.pending


def test_request_identity_accepts_matching_active_membership() -> None:
    tenant = Tenant.build(slug="agency-one", display_name="Agency One", now=NOW)
    user = AuthenticatedUser.build(
        email="owner@example.com",
        display_name="Owner",
        now=NOW,
    )
    membership = TenantMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        role=TenantRole.owner,
        created_at=NOW,
    )
    identity = RequestIdentity(
        user_id=user.id,
        tenant_id=tenant.id,
        membership_role=TenantRole.owner,
        session_id="s" * 24,
        authenticated_at=NOW,
    )

    require_active_membership(identity, membership)


def test_request_identity_rejects_inactive_or_mismatched_membership() -> None:
    identity = RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.analyst,
        session_id="s" * 24,
        authenticated_at=NOW,
    )

    with pytest.raises(IdentityBoundaryError, match="inactive"):
        require_active_membership(
            identity,
            TenantMembership(
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                role=identity.membership_role,
                active=False,
                created_at=NOW,
            ),
        )

    with pytest.raises(IdentityBoundaryError, match="does not match"):
        require_active_membership(
            identity,
            TenantMembership(
                tenant_id="c" * 24,
                user_id=identity.user_id,
                role=identity.membership_role,
                created_at=NOW,
            ),
        )


def test_cross_tenant_object_access_is_rejected() -> None:
    identity = RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.viewer,
        session_id="s" * 24,
        authenticated_at=NOW,
    )
    same_tenant = TenantObjectRef(
        tenant_id=identity.tenant_id,
        object_type="project",
        object_id="project-1",
    )
    other_tenant = TenantObjectRef(
        tenant_id="c" * 24,
        object_type="project",
        object_id="project-1",
    )

    require_tenant_scope(identity, same_tenant)
    with pytest.raises(IdentityBoundaryError, match="Cross-tenant"):
        require_tenant_scope(identity, other_tenant)
