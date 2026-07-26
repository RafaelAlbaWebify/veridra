from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.identity_bootstrap import (
    BOOTSTRAP_CONFIRMATION,
    IdentityBootstrapError,
    SQLiteIdentityBootstrap,
)
from veridra.password_auth import SQLitePasswordAuthenticator

NOW = datetime(2026, 7, 25, 10, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery-staple"


def _create(database: Path) -> None:
    SQLiteIdentityBootstrap(database).create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password=PASSWORD,
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )


def test_bootstrap_creates_verified_owner_and_login_records(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"

    _create(database)

    records = SQLitePasswordAuthenticator(database).authenticate(
        email="owner@example.com",
        tenant_slug="customer-one",
        password=PASSWORD,
    )
    assert records is not None
    assert records.user.status.value == "active"
    assert records.user.email_verified_at == NOW
    assert records.membership.role.value == "owner"
    assert records.tenant.slug == "customer-one"


def test_bootstrap_refuses_invalid_confirmation_and_existing_identity(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    bootstrap = SQLiteIdentityBootstrap(database)

    with pytest.raises(IdentityBootstrapError, match="confirmation"):
        bootstrap.create_first_owner(
            tenant_slug="customer-one",
            tenant_name="Customer one",
            owner_email="owner@example.com",
            owner_name="Owner",
            password=PASSWORD,
            confirmation="wrong-token",
            created_at=NOW,
        )

    _create(database)
    with pytest.raises(IdentityBootstrapError, match="already"):
        _create(database)


def test_bootstrap_rolls_back_all_records_when_final_insert_fails(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    bootstrap = SQLiteIdentityBootstrap(database)
    bootstrap.initialize()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TRIGGER reject_bootstrap_password
            BEFORE INSERT ON password_credentials
            BEGIN
                SELECT RAISE(ABORT, 'password insert rejected');
            END"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="password insert rejected"):
        _create(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM password_credentials").fetchone()[0] == 0
