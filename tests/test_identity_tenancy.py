from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    AuthSession,
    IdentityBoundaryError,
    RequestIdentity,
    SessionStatus,
    Tenant,
    TenantMembership,
    TenantObjectRef,
    TenantRole,
    TenantStatus,
    build_request_identity,
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


def _active_identity_records() -> tuple[
    AuthenticatedUser,
    Tenant,
    TenantMembership,
    AuthSession,
]:
    tenant = Tenant.build(slug="agency-one", display_name="Agency One", now=NOW)
    user = AuthenticatedUser.build(
        email="owner@example.com",
        display_name="Owner",
        now=NOW,
    ).model_copy(
        update={
            "status": AccountStatus.active,
            "email_verified_at": NOW,
        }
    )
    membership = TenantMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        role=TenantRole.owner,
        created_at=NOW,
    )
    session = AuthSession(
        id="s" * 24,
        user_id=user.id,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=8),
    )
    return user, tenant, membership, session


def test_request_identity_is_built_from_verified_active_records() -> None:
    user, tenant, membership, session = _active_identity_records()

    identity = build_request_identity(
        user=user,
        tenant=tenant,
        membership=membership,
        session=session,
        now=NOW + timedelta(minutes=1),
    )

    assert identity.user_id == user.id
    assert identity.tenant_id == tenant.id
    assert identity.membership_role == TenantRole.owner
    assert identity.session_id == session.id


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"user_status": AccountStatus.disabled}, "account is not active"),
        ({"email_verified_at": None}, "email is not verified"),
        ({"tenant_status": TenantStatus.suspended}, "Tenant is not active"),
        ({"membership_active": False}, "membership is inactive"),
        ({"session_status": SessionStatus.revoked}, "Session has been revoked"),
        ({"session_expired": True}, "Session has expired"),
    ],
)
def test_request_identity_rejects_invalid_lifecycle_state(
    change: dict[str, object],
    message: str,
) -> None:
    user, tenant, membership, session = _active_identity_records()
    if "user_status" in change:
        user = user.model_copy(update={"status": change["user_status"]})
    if "email_verified_at" in change:
        user = user.model_copy(update={"email_verified_at": change["email_verified_at"]})
    if "tenant_status" in change:
        tenant = tenant.model_copy(update={"status": change["tenant_status"]})
    if "membership_active" in change:
        membership = membership.model_copy(update={"active": change["membership_active"]})
    if "session_status" in change:
        session = session.model_copy(
            update={
                "status": change["session_status"],
                "revoked_at": NOW,
            }
        )
    if change.get("session_expired"):
        session = session.model_copy(update={"expires_at": NOW})

    with pytest.raises(IdentityBoundaryError, match=message):
        build_request_identity(
            user=user,
            tenant=tenant,
            membership=membership,
            session=session,
            now=NOW + timedelta(minutes=1),
        )
