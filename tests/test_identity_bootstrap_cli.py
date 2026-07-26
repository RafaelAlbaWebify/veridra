from __future__ import annotations

from pathlib import Path

import pytest

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION
from veridra.identity_bootstrap_cli import main
from veridra.password_auth import SQLitePasswordAuthenticator

PASSWORD = "correct-horse-battery-staple"


def _args(database: Path) -> list[str]:
    return [
        "--database",
        str(database),
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


def test_cli_bootstraps_without_password_in_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "identity.sqlite3"
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))

    result = main(_args(database))

    assert result == 0
    assert "Bootstrap complete" in capsys.readouterr().out
    records = SQLitePasswordAuthenticator(database).authenticate(
        email="owner@example.com",
        tenant_slug="customer-one",
        password=PASSWORD,
    )
    assert records is not None
    assert PASSWORD not in _args(database)


def test_cli_rejects_password_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    answers = iter([PASSWORD, "different-password-value"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))

    result = main(_args(tmp_path / "identity.sqlite3"))

    assert result == 2
    assert "Passwords do not match" in capsys.readouterr().out
