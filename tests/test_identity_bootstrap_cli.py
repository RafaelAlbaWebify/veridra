from __future__ import annotations

from pathlib import Path

import pytest

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION
from veridra.identity_bootstrap_cli import main
from veridra.password_auth import SQLitePasswordAuthenticator
from veridra.workspace_policy import PlanName, WorkspaceStore

PASSWORD = "correct-horse-battery-staple"


def _args(database: Path, tenant_data_root: Path) -> list[str]:
    return [
        "--database",
        str(database),
        "--tenant-data-root",
        str(tenant_data_root),
        "--tenant-slug",
        "customer-one",
        "--tenant-name",
        "Customer one",
        "--owner-email",
        "owner@example.com",
        "--owner-name",
        "Owner",
        "--confirm",
        BOOTSTRAP_CONFIRMATION,
    ]


def test_cli_bootstraps_owner_and_free_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "identity.sqlite3"
    tenant_data_root = tmp_path / "tenants"
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))

    result = main(_args(database, tenant_data_root))

    assert result == 0
    output = capsys.readouterr().out
    assert "Bootstrap complete" in output
    records = SQLitePasswordAuthenticator(database).authenticate(
        email="owner@example.com",
        tenant_slug="customer-one",
        password=PASSWORD,
    )
    assert records is not None
    workspace = WorkspaceStore(
        tenant_data_root / records.tenant.id / "workspace"
    ).load()
    assert workspace.plan == PlanName.free
    assert workspace.display_name == "Customer one"
    assert PASSWORD not in _args(database, tenant_data_root)


def test_cli_rejects_password_mismatch_without_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    answers = iter([PASSWORD, "different-password-value"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))
    tenant_data_root = tmp_path / "tenants"

    result = main(_args(tmp_path / "identity.sqlite3", tenant_data_root))

    assert result == 2
    assert "Passwords do not match" in capsys.readouterr().out
    assert not tenant_data_root.exists()
