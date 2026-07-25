from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.existing_user_invitations import SQLiteExistingUserInvitationService
from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    Tenant,
    TenantMembership,
    TenantRole,
)
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.tenant_invitations import TenantInvitationError

NOW = datetime(2026, 7, 26, 2, 0, tzinfo=UTC)


def _active_user(email: str, name: str) -> AuthenticatedUser:
    return AuthenticatedUser.build(
        email=email,
        display_name=name,
        now=NOW,
    ).model_copy(
        update={"status": AccountStatus.active, "email_verified_at": NOW}
    )


def _setup(
    database: Path,
) -> tuple[Tenant, AuthenticatedUser, AuthenticatedUser, AuthenticatedUser]:
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    target = Tenant.build(slug="target-tenant", display_name="Target", now=NOW)
    source = Tenant.build(slug="source-tenant", display_name="Source", now=NOW)
    owner = _active_user("owner@example.com", "Owner")
    existing = _active_user("existing@example.com", "Existing user")
    other = _active_user("other@example.com", "Other user")
    for tenant in (target, source):
        store.save_tenant(tenant)
    for user in (owner, existing, other):
        store.save_user(user)
    store.save_membership(
        TenantMembership(
            tenant_id=target.id,
            user_id=owner.id,
            role=TenantRole.owner,
            active=True,
            created_at=NOW,
        )
    )
    for user in (existing, other):
        store.save_membership(
            TenantMembership(
                tenant_id=source.id,
                user_id=user.id,
                role=TenantRole.viewer,
                active=True,
                created_at=NOW,
            )
        )
    return target, owner, existing, other


def _membership(database: Path, tenant_id: str, user_id: str) -> sqlite3.Row | None:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            """SELECT role, active FROM memberships
            WHERE tenant_id = ? AND user_id = ?""",
            (tenant_id, user_id),
        ).fetchone()
    finally:
        connection.close()


def test_existing_user_accepts_matching_invitation_once(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    target, owner, existing, _ = _setup(database)
    service = SQLiteExistingUserInvitationService(database)
    issued = service.issue(
        tenant_id=target.id,
        created_by_user_id=owner.id,
        email=str(existing.email),
        role=TenantRole.analyst,
        now=NOW,
    )

    accepted = service.accept(
        token=issued.token,
        user_id=existing.id,
        now=NOW,
    )

    assert accepted.tenant_id == target.id
    assert accepted.user_id == existing.id
    assert accepted.role is TenantRole.analyst
    membership = _membership(database, target.id, existing.id)
    assert membership is not None
    assert membership["role"] == TenantRole.analyst.value
    assert bool(membership["active"])
    with pytest.raises(TenantInvitationError, match="already used"):
        service.accept(
            token=issued.token,
            user_id=existing.id,
            now=NOW,
        )


def test_wrong_authenticated_account_cannot_consume_invitation(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    target, owner, existing, other = _setup(database)
    service = SQLiteExistingUserInvitationService(database)
    issued = service.issue(
        tenant_id=target.id,
        created_by_user_id=owner.id,
        email=str(existing.email),
        role=TenantRole.viewer,
        now=NOW,
    )

    with pytest.raises(TenantInvitationError, match="does not match"):
        service.accept(token=issued.token, user_id=other.id, now=NOW)

    assert _membership(database, target.id, other.id) is None
    accepted = service.accept(token=issued.token, user_id=existing.id, now=NOW)
    assert accepted.user_id == existing.id


def test_existing_invitation_requires_verified_user_and_new_membership(
    tmp_path: Path,
) -> None:
    database = tmp_path / "identity.sqlite3"
    target, owner, existing, _ = _setup(database)
    service = SQLiteExistingUserInvitationService(database)

    with pytest.raises(TenantInvitationError, match="already belongs"):
        service.issue(
            tenant_id=target.id,
            created_by_user_id=owner.id,
            email=str(owner.email),
            role=TenantRole.viewer,
            now=NOW,
        )

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE users SET email_verified_at = NULL WHERE id = ?",
            (existing.id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(TenantInvitationError, match="verified existing user"):
        service.issue(
            tenant_id=target.id,
            created_by_user_id=owner.id,
            email=str(existing.email),
            role=TenantRole.viewer,
            now=NOW,
        )
