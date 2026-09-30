from __future__ import annotations

import sqlite3
from pathlib import Path

from veridra.local_operator_bootstrap import ensure_local_operator


def test_local_operator_bootstrap_creates_valid_webify_owner(tmp_path: Path) -> None:
    database = tmp_path / "identity" / "veridra.sqlite3"
    tenant_root = tmp_path / "tenants"

    assert ensure_local_operator(database, tenant_root) is True
    assert ensure_local_operator(database, tenant_root) is False

    with sqlite3.connect(database) as connection:
        email = connection.execute("SELECT email FROM users").fetchone()[0]
        tenant = connection.execute("SELECT slug FROM tenants").fetchone()[0]

    assert email == "operator@webify.ie"
    assert tenant == "webify"
