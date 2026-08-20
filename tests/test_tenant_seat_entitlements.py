from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.existing_user_invitations import SQLiteExistingUserInvitationService
from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    Tenant,
    TenantMembership,
    TenantRole,
)
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.tenant_invitations import SQLiteTenantInvitationService, TenantInvitationError
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore

NOW = datetime(2026, 8, 20, 12, 30, tzinfo=UTC)
PASSWORD = "invited-correct-horse-battery"


def _bootstrap(database: Path) -> tuple[str, str]:
    result = SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password="owner-correct-horse-battery",
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )
    return result.tenant_id, result.user_id


def _workspace(root: Path, tenant_id: str, plan: PlanName) -> None:
    WorkspaceStore(root / tenant_id / "workspace").save(WorkspaceConfig(plan=plan))


def _active_members(database: Path, tenant_id: str) -> int:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM memberships WHERE tenant_id = ? AND active = 1",
            (tenant_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _user_exists(database: Path, email: str) -> bool:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    return row is not None


def test_new_user_acceptance_is_atomic_at_plan_seat_limit(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    root = tmp_path / "tenants"
    tenant_id, owner_id = _bootstrap(database)
    service = SQLiteTenantInvitationService(database, root)
    _workspace(root, tenant_id, PlanName.free)

    first = service.issue(
        tenant_id=tenant_id,
        created_by_user_id=owner_id,
        email="first@example.com",
        role=TenantRole.analyst,
        now=NOW,
    )
    with pytest.raises(TenantInvitationError, match="seat allowance"):
        service.accept(
            token=first.token,
            display_name="First user",
            password=PASSWORD,
            now=NOW,
        )

    assert _active_members(database, tenant_id) == 1
    assert not _user_exists(database, "first@example.com")
    assert len(service.list_active(tenant_id=tenant_id, now=NOW)) == 1

    _workspace(root, tenant_id, PlanName.professional)
    accepted = service.accept(
        token=first.token,
        display_name="First user",
        password=PASSWORD,
        now=NOW,
    )
    assert accepted.tenant_id == tenant_id

    second = service.issue(
        tenant_id=tenant_id,
        created_by_user_id=owner_id,
        email="second@example.com",
        role=TenantRole.viewer,
        now=NOW,
    )
    service.accept(
        token=second.token,
        display_name="Second user",
        password=PASSWORD,
        now=NOW,
    )
    assert _active_members(database, tenant_id) == 3

    third = service.issue(
        tenant_id=tenant_id,
        created_by_user_id=owner_id,
        email="third@example.com",
        role=TenantRole.sales,
        now=NOW,
    )
    with pytest.raises(TenantInvitationError, match="seat allowance"):
        service.accept(
            token=third.token,
            display_name="Third user",
            password=PASSWORD,
            now=NOW,
        )
    assert _active_members(database, tenant_id) == 3
    assert not _user_exists(database, "third@example.com")


def test_existing_user_acceptance_respects_target_tenant_seats(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    root = tmp_path / "tenants"
    target_id, owner_id = _bootstrap(database)
    store = SQLiteIdentityRecordStore(database)
    source = Tenant.build(slug="source", display_name="Source", now=NOW)
    existing = AuthenticatedUser.build(
        email="existing@example.com",
        display_name="Existing",
        now=NOW,
    ).model_copy(update={"status": AccountStatus.active, "email_verified_at": NOW})
    store.save_tenant(source)
    store.save_user(existing)
    store.save_membership(
        TenantMembership(
            tenant_id=source.id,
            user_id=existing.id,
            role=TenantRole.viewer,
            active=True,
            created_at=NOW,
        )
    )
    service = SQLiteExistingUserInvitationService(database, root)
    invitation = service.issue(
        tenant_id=target_id,
        created_by_user_id=owner_id,
        email=str(existing.email),
        role=TenantRole.analyst,
        now=NOW,
    )
    _workspace(root, target_id, PlanName.free)

    with pytest.raises(TenantInvitationError, match="seat allowance"):
        service.accept(token=invitation.token, user_id=existing.id, now=NOW)
    assert _active_members(database, target_id) == 1

    _workspace(root, target_id, PlanName.professional)
    accepted = service.accept(token=invitation.token, user_id=existing.id, now=NOW)
    assert accepted.tenant_id == target_id
    assert accepted.user_id == existing.id
    assert _active_members(database, target_id) == 2


def test_unconfigured_tenant_policy_preserves_invitation_compatibility(
    tmp_path: Path,
) -> None:
    database = tmp_path / "identity.sqlite3"
    root = tmp_path / "tenants"
    tenant_id, owner_id = _bootstrap(database)
    service = SQLiteTenantInvitationService(database, root)
    invitation = service.issue(
        tenant_id=tenant_id,
        created_by_user_id=owner_id,
        email="compat@example.com",
        role=TenantRole.viewer,
        now=NOW,
    )

    accepted = service.accept(
        token=invitation.token,
        display_name="Compatibility user",
        password=PASSWORD,
        now=NOW,
    )

    assert accepted.tenant_id == tenant_id
    assert _active_members(database, tenant_id) == 2
