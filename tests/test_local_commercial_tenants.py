from __future__ import annotations

import sqlite3
from pathlib import Path

from veridra.local_commercial_tenants import list_local_commercial_tenants
from veridra.workspace_policy import PlanName, WorkspaceConfig, WorkspaceStatus, WorkspaceStore

TENANT_A = "a" * 24
TENANT_B = "b" * 24


def _identity_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE tenants (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO tenants (id, slug, display_name, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    TENANT_A,
                    "alpha",
                    "Alpha Agency",
                    "active",
                    "2026-10-02T20:00:00+00:00",
                ),
                (
                    TENANT_B,
                    "beta",
                    "Beta Agency",
                    "active",
                    "2026-10-02T20:01:00+00:00",
                ),
            ],
        )


def test_local_commercial_tenant_listing_exposes_only_safe_workspace_summary(
    tmp_path: Path,
) -> None:
    database = tmp_path / "identity.sqlite3"
    root = tmp_path / "tenants"
    _identity_database(database)
    WorkspaceStore(root / TENANT_A / "workspace").save(
        WorkspaceConfig(
            display_name="Alpha Agency",
            plan=PlanName.professional,
            status=WorkspaceStatus.active,
        )
    )

    result = list_local_commercial_tenants(
        identity_database=database,
        tenant_root=root,
    )

    assert result == [
        {
            "tenant_id": TENANT_A,
            "slug": "alpha",
            "display_name": "Alpha Agency",
            "tenant_status": "active",
            "workspace": {
                "plan": "professional",
                "status": "active",
            },
        },
        {
            "tenant_id": TENANT_B,
            "slug": "beta",
            "display_name": "Beta Agency",
            "tenant_status": "active",
            "workspace": None,
        },
    ]
