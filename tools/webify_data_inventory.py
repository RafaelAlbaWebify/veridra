"""Read-only inventory of private Webify data and historical SaaS residue.

Example:
  python tools/webify_data_inventory.py --identity-db PATH --tenant-root PATH
This command never writes into the supplied data directories.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote


def inspect_identity(database: Path) -> dict[str, object]:
    if not database.is_file():
        return {"state": "missing", "tables": {}, "integrity": "not_checked"}
    # immutable=1 is safe only for a closed, consistent snapshot. Refuse live
    # WAL sidecars rather than silently ignore uncheckpointed transactions.
    sidecars = [
        Path(str(database) + suffix)
        for suffix in ("-wal", "-shm", "-journal")
        if Path(str(database) + suffix).exists()
    ]
    if sidecars:
        return {
            "state": "unsafe_snapshot",
            "tables": {},
            "integrity": "not_checked",
            "warning": "SQLite sidecar files detected; use a consistent offline backup.",
        }
    uri = "file:" + quote(database.resolve().as_posix(), safe="/:") + "?mode=ro&immutable=1"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            counts = {
                name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for name in ("users", "tenants")
                if name in tables
            }
        return {"state": "readable", "tables": counts, "integrity": integrity}
    except (sqlite3.Error, OSError) as exc:
        return {"state": "unreadable", "tables": {}, "integrity": type(exc).__name__}


def inventory(identity_database: Path, tenant_root: Path) -> dict[str, object]:
    identity_database = identity_database.expanduser().resolve()
    tenant_root = tenant_root.expanduser().resolve()
    result: dict[str, object] = {
        "identity": inspect_identity(identity_database),
        "tenant_root_exists": tenant_root.is_dir(),
        "tenant_directories": 0,
        "projects": 0,
        "assessments": 0,
        "legacy_workspace_configs": 0,
        "legacy_plan_events": 0,
        "legacy_saas_stripe_bindings": 0,
        "warnings": [],
    }
    if not tenant_root.is_dir():
        result["warnings"] = ["Tenant data root does not exist."]
        return result
    tenants = [
        p for p in tenant_root.iterdir()
        if p.is_dir() and not p.is_symlink() and len(p.name) == 24
        and all(c in "0123456789abcdef" for c in p.name)
    ]
    result["tenant_directories"] = len(tenants)
    for tenant in tenants:
        result["projects"] += len(list((tenant / "projects").glob("*.json")))
        result["assessments"] += len(
            list((tenant / "projects").glob("*/assessments/*.json"))
        )
        workspace = tenant / "workspace"
        result["legacy_workspace_configs"] += int(
            (workspace / "workspace.json").is_file()
        )
        result["legacy_plan_events"] += len(
            list((workspace / "plan-changes").glob("*.json"))
        )
        result["legacy_saas_stripe_bindings"] += int(
            (workspace / "billing" / "stripe.json").is_file()
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-db", type=Path, required=True)
    parser.add_argument("--tenant-root", type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.identity_db, args.tenant_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["identity"]["state"] == "readable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
