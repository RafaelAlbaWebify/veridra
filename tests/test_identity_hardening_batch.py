from __future__ import annotations

import sqlite3
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
from veridra.sqlite_identity_store import SQLiteIdentityRecordStore
from veridra.sqlite_schema_versions import (
    SQLiteSchemaVersionManager,
    SchemaMigrationError,
)
from veridra.sqlite_session_manager import (
    SQLiteSessionManager,
    SessionManagementError,
)

NOW = datetime(2026, 7, 26, 4, 0, tzinfo=UTC)


def _identity_database(tmp_path: Path) -> tuple[Path, AuthenticatedUser, Tenant]:
    database = tmp_path / "identity.sqlite3"
    store = SQLiteIdentityRecordStore(database)
    store.initialize()
    tenant = Tenant.build(slug="customer", display_name="Customer", now=NOW)
    user = AuthenticatedUser.build(
        email="person@example.com",
        display_name="Person",
        now=NOW,
    ).model_copy(
        update={"status": AccountStatus.active, "email_verified_at": NOW}
    )
    store.save_tenant(tenant)
    store.save_user(user)
    store.save_membership(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=TenantRole.analyst,
            active=True,
            created_at=NOW,
        )
    )
    return database, user, tenant


def _save_session(
    database: Path,
    *,
    user: AuthenticatedUser,
    tenant: Tenant,
    session_id: str,
    credential: str,
    issued_at: datetime,
) -> None:
    SQLiteIdentityRecordStore(database).save_session(
        credential=credential,
        tenant_id=tenant.id,
        session=AuthSession(
            id=session_id,
            user_id=user.id,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=8),
        ),
    )


def test_schema_migrations_normalize_email_and_are_idempotent(
    tmp_path: Path,
) -> None:
    database, user, _ = _identity_database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE users SET email = ? WHERE id = ?",
            (" Person@Example.COM ", user.id),
        )

    manager = SQLiteSchemaVersionManager(database)

    assert manager.apply_all(applied_at=NOW) == (1,)
    assert manager.apply_all(applied_at=NOW + timedelta(minutes=1)) == ()
    assert [item.version for item in manager.list_applied()] == [1]
    with sqlite3.connect(database) as connection:
        email = connection.execute(
            "SELECT email FROM users WHERE id = ?",
            (user.id,),
        ).fetchone()
    assert email is not None
    assert email[0] == "person@example.com"


def test_schema_migration_rejects_normalized_email_collision(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL,
                email_verified_at TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        connection.executemany(
            """INSERT INTO users
            (id, email, display_name, status, email_verified_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (
                    "e" * 24,
                    "person@example.com",
                    "First",
                    AccountStatus.active.value,
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
                (
                    "f" * 24,
                    " PERSON@EXAMPLE.COM ",
                    "Duplicate",
                    AccountStatus.active.value,
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            ),
        )

    with pytest.raises(SchemaMigrationError):
        SQLiteSchemaVersionManager(database).apply_all(applied_at=NOW)


def test_session_manager_lists_rotates_and_revokes_only_owned_sessions(
    tmp_path: Path,
) -> None:
    database, user, tenant = _identity_database(tmp_path)
    current_id = "a" * 24
    other_id = "b" * 24
    _save_session(
        database,
        user=user,
        tenant=tenant,
        session_id=current_id,
        credential="c" * 48,
        issued_at=NOW,
    )
    _save_session(
        database,
        user=user,
        tenant=tenant,
        session_id=other_id,
        credential="d" * 48,
        issued_at=NOW + timedelta(minutes=1),
    )
    manager = SQLiteSessionManager(database)

    listed = manager.list_for_user(
        user_id=user.id,
        current_session_id=current_id,
    )
    assert [item.id for item in listed] == [other_id, current_id]
    assert next(item for item in listed if item.id == current_id).current

    manager.revoke_for_user(
        user_id=user.id,
        session_id=other_id,
        current_session_id=current_id,
        revoked_at=NOW + timedelta(minutes=2),
    )
    assert manager.list_for_user(
        user_id=user.id,
        current_session_id=current_id,
    )[0].status is SessionStatus.revoked
    with pytest.raises(SessionManagementError, match="logout"):
        manager.revoke_for_user(
            user_id=user.id,
            session_id=current_id,
            current_session_id=current_id,
            revoked_at=NOW + timedelta(minutes=3),
        )

    replacement = AuthSession(
        id="e" * 24,
        user_id=user.id,
        issued_at=NOW + timedelta(minutes=4),
        expires_at=NOW + timedelta(hours=8),
    )
    manager.rotate(
        current_session_id=current_id,
        tenant_id=tenant.id,
        replacement_credential="f" * 48,
        replacement_session=replacement,
        revoked_at=replacement.issued_at,
    )
    final = manager.list_for_user(
        user_id=user.id,
        current_session_id=replacement.id,
    )
    assert next(
        item for item in final if item.id == current_id
    ).status is SessionStatus.revoked
    assert next(item for item in final if item.id == replacement.id).current
