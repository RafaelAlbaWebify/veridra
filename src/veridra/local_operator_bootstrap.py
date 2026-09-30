from __future__ import annotations

import argparse
import secrets
import sqlite3
from pathlib import Path

from .identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap


def _has_identity(database: Path) -> bool:
    if not database.exists():
        return False
    try:
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            if not row or int(row[0]) == 0:
                return False
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]) > 0
    except sqlite3.Error:
        return False


def ensure_local_operator(database: Path, tenant_data_root: Path) -> bool:
    """Create the sole operator identity for a fresh operator-local installation.

    Returns True when a new identity was created and False when an existing identity
    database was preserved unchanged.
    """

    if _has_identity(database):
        return False

    bootstrap = SQLiteIdentityBootstrap(
        database,
        tenant_data_root=tenant_data_root,
    )
    bootstrap.create_first_owner(
        tenant_slug="webify",
        tenant_name="Webify",
        owner_email="operator@webify.ie",
        owner_name="Webify Operator",
        password=secrets.token_urlsafe(48),
        confirmation=BOOTSTRAP_CONFIRMATION,
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="veridra-local-operator-bootstrap",
        description="Ensure the single operator identity exists for operator-local VERIDRA.",
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--tenant-data-root", required=True, type=Path)
    args = parser.parse_args(argv)

    created = ensure_local_operator(
        args.database.expanduser().resolve(),
        args.tenant_data_root.expanduser().resolve(),
    )
    print("local_operator_bootstrap=" + ("created" if created else "existing"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
