from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from .workspace_policy import WorkspaceStore


class LocalCommercialTenantListError(RuntimeError):
    pass


def list_local_commercial_tenants(
    *,
    identity_database: Path,
    tenant_root: Path,
) -> list[dict[str, object]]:
    database = identity_database.expanduser().resolve()
    root = tenant_root.expanduser().resolve()
    if not database.exists():
        raise LocalCommercialTenantListError("Commercial identity database was not found.")

    try:
        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT id, slug, display_name, status, created_at
                FROM tenants
                ORDER BY created_at, slug
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise LocalCommercialTenantListError(
            "Commercial tenant records could not be read safely."
        ) from exc

    result: list[dict[str, object]] = []
    for row in rows:
        tenant_id = str(row["id"])
        workspace_store = WorkspaceStore(root / tenant_id / "workspace")
        workspace = workspace_store.load() if workspace_store.path.exists() else None
        result.append(
            {
                "tenant_id": tenant_id,
                "slug": str(row["slug"]),
                "display_name": str(row["display_name"]),
                "tenant_status": str(row["status"]),
                "workspace": (
                    {
                        "plan": workspace.plan.value,
                        "status": workspace.status.value,
                    }
                    if workspace is not None
                    else None
                ),
            }
        )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "List local commercial tenant/workspace identifiers without exposing "
            "credentials or session data."
        )
    )
    parser.add_argument("--identity-db", type=Path, default=None)
    parser.add_argument("--tenant-data-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    identity = args.identity_db or os.environ.get("VERIDRA_IDENTITY_DB")
    tenant_root = args.tenant_data_root or os.environ.get("VERIDRA_TENANT_DATA_ROOT")
    if identity is None or tenant_root is None:
        raise SystemExit(
            "VERIDRA_IDENTITY_DB and VERIDRA_TENANT_DATA_ROOT are required."
        )
    try:
        tenants = list_local_commercial_tenants(
            identity_database=Path(identity),
            tenant_root=Path(tenant_root),
        )
    except LocalCommercialTenantListError as exc:
        raise SystemExit(f"status=failed error={exc}") from exc

    if args.json:
        print(json.dumps({"tenants": tenants}, indent=2, sort_keys=True))
        return

    if not tenants:
        print("No local commercial tenants were found.")
        return

    print("TENANT_ID                  PLAN          STATUS       NAME")
    for item in tenants:
        workspace = item["workspace"]
        if isinstance(workspace, dict):
            plan = str(workspace["plan"])
            status = str(workspace["status"])
        else:
            plan = "missing"
            status = "missing"
        print(
            f"{item['tenant_id']}  {plan:<12}  {status:<11}  "
            f"{item['display_name']}"
        )


if __name__ == "__main__":
    main()
