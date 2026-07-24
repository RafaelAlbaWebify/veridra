from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from veridra.identity_tenancy import (
    AccountStatus,
    AuthenticatedUser,
    AuthSession,
    SessionStatus,
    Tenant,
    TenantMembership,
    TenantRole,
)
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore, SQLiteIdentityStoreError

NOW = datetime(2026, 7, 24, 19, 0, tzinfo=UTC)
CREDENTIAL = "opaque-session-credential-value-000001"


def _records(store: SQLiteIdentityRecordStore, tenant_slug: str = "primary") -> tuple[Tenant, AuthenticatedUser, AuthSession]:
    tenant = Tenant.build(slug=tenant_slug, display_name=tenant_slug.title(), now=NOW)
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
        id="session-sqlite-identity-store-001",
        user_id=user.id,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=8),
    )
    store.save_tenant(tenant)
    store.save_user(user)
    store.save_membership(membership)
    return tenant, user, session


@pytest.mark.asyncio
async def test_round_trip_uses_hashed_credential_and_tenant_binding(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    tenant, user, session = _records(store)

    store.save_session(credential=CREDENTIAL, tenant_id=tenant.id, session=session)
    records = await store.load_by_credential(CREDENTIAL)

    assert records is not None
    assert records.user == user
    assert records.tenant == tenant
    assert records.membership.role == TenantRole.owner
    assert records.session == session
    assert CREDENTIAL.encode("utf-8") not in database.read_bytes()


@pytest.mark.asyncio
async def test_unknown_and_short_credentials_fail_closed(tmp_path: Path) -> None:
    store = SQLiteIdentityRecordStore(tmp_path / "identity.sqlite3")
    store.initialize()

    assert await store.load_by_credential("short") is None
    assert await store.load_by_credential("x" * 40) is None


@pytest.mark.asyncio
async def test_revocation_is_durable_and_returned_from_current_records(tmp_path: Path) -> None:
    store = SQLiteIdentityRecordStore(tmp_path / "identity.sqlite3")
    store.initialize()
    tenant, _, session = _records(store)
    store.save_session(credential=CREDENTIAL, tenant_id=tenant.id, session=session)

    store.revoke_session(session.id, revoked_at=NOW + timedelta(minutes=5))
    records = await store.load_by_credential(CREDENTIAL)

    assert records is not None
    assert records.session.status == SessionStatus.revoked
    assert records.session.revoked_at == NOW + timedelta(minutes=5)


def test_session_requires_existing_tenant_membership(tmp_path: Path) -> None:
    store = SQLiteIdentityRecordStore(tmp_path / "identity.sqlite3")
    store.initialize()
    tenant, _, session = _records(store)
    other_tenant = Tenant.build(slug="other", display_name="Other", now=NOW)
    store.save_tenant(other_tenant)

    with pytest.raises(Exception, match="FOREIGN KEY"):
        store.save_session(
            credential=CREDENTIAL,
            tenant_id=other_tenant.id,
            session=session,
        )

    store.save_session(credential=CREDENTIAL, tenant_id=tenant.id, session=session)


def test_revoke_unknown_session_is_explicit(tmp_path: Path) -> None:
    store = SQLiteIdentityRecordStore(tmp_path / "identity.sqlite3")
    store.initialize()

    with pytest.raises(SQLiteIdentityStoreError, match="not found"):
        store.revoke_session("missing-session-identifier", revoked_at=NOW)


@pytest.mark.asyncio
async def test_one_user_can_hold_distinct_tenant_bound_sessions(tmp_path: Path) -> None:
    store = SQLiteIdentityRecordStore(tmp_path / "identity.sqlite3")
    store.initialize()
    tenant_a, user, session_a = _records(store, "tenant-a")
    tenant_b = Tenant.build(slug="tenant-b", display_name="Tenant B", now=NOW)
    membership_b = TenantMembership(
        tenant_id=tenant_b.id,
        user_id=user.id,
        role=TenantRole.viewer,
        created_at=NOW,
    )
    session_b = session_a.model_copy(update={"id": "session-sqlite-identity-store-002"})
    store.save_tenant(tenant_b)
    store.save_membership(membership_b)
    store.save_session(credential="a" * 40, tenant_id=tenant_a.id, session=session_a)
    store.save_session(credential="b" * 40, tenant_id=tenant_b.id, session=session_b)

    records_a = await store.load_by_credential("a" * 40)
    records_b = await store.load_by_credential("b" * 40)

    assert records_a is not None and records_a.tenant.id == tenant_a.id
    assert records_a.membership.role == TenantRole.owner
    assert records_b is not None and records_b.tenant.id == tenant_b.id
    assert records_b.membership.role == TenantRole.viewer
