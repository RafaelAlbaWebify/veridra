from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap
from veridra.identity_tenancy import Tenant
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStore

NOW = datetime(2026, 7, 27, 19, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery-staple"


def _create(bootstrap: SQLiteIdentityBootstrap) -> None:
    bootstrap.create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password=PASSWORD,
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )


def test_direct_bootstrap_creates_free_tenant_workspace(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    tenant_root = tmp_path / "tenants"
    bootstrap = SQLiteIdentityBootstrap(database, tenant_data_root=tenant_root)

    result = bootstrap.create_first_owner(
        tenant_slug="customer-one",
        tenant_name="Customer one",
        owner_email="owner@example.com",
        owner_name="Owner",
        password=PASSWORD,
        confirmation=BOOTSTRAP_CONFIRMATION,
        created_at=NOW,
    )

    workspace = WorkspaceStore(tenant_root / result.tenant_id / "workspace").load()
    assert workspace.plan == PlanName.free
    assert workspace.display_name == "Customer one"


def test_workspace_failure_rolls_back_identity_and_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "identity.sqlite3"
    tenant_root = tmp_path / "tenants"
    bootstrap = SQLiteIdentityBootstrap(database, tenant_data_root=tenant_root)
    original_save = WorkspaceStore.save

    def fail_after_write(store: WorkspaceStore, workspace: WorkspaceConfig) -> None:
        original_save(store, workspace)
        raise OSError("workspace write failed")

    monkeypatch.setattr(WorkspaceStore, "save", fail_after_write)

    with pytest.raises(OSError, match="workspace write failed"):
        _create(bootstrap)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM password_credentials"
        ).fetchone()[0] == 0

    tenant = Tenant.build(
        slug="customer-one",
        display_name="Customer one",
        now=NOW,
    )
    workspace_path = tenant_root / tenant.id / "workspace" / "workspace.json"
    assert not workspace_path.exists()
