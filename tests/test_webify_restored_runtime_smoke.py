from __future__ import annotations

import runpy
from pathlib import Path

_module = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "tools" / "webify_restored_runtime_smoke.py")
)
check_restored_runtime = _module["check_restored_runtime"]


def test_restored_smoke_fails_closed_without_snapshot(tmp_path: Path) -> None:
    result = check_restored_runtime(tmp_path / "no.sqlite3", tmp_path / "tenants")
    assert result["result"] == "blocked"
    assert not list(tmp_path.iterdir())


def test_restored_smoke_refuses_sqlite_wal_sidecars(tmp_path: Path) -> None:
    db = tmp_path / "identity.sqlite3"
    db.write_bytes(b"closed snapshot placeholder")
    (tmp_path / "tenants").mkdir()
    wal = Path(str(db) + "-wal")
    wal.write_bytes(b"pending transactions")
    result = check_restored_runtime(db, tmp_path / "tenants")
    assert result["result"] == "blocked"
    assert wal.read_bytes() == b"pending transactions"
