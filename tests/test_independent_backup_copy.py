from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[1] / "tools" / "independent_backup_copy.py"
SPEC = importlib.util.spec_from_file_location("independent_backup_copy", FILE)
assert SPEC and SPEC.loader
copy_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(copy_tool)


def test_secondary_copy_is_verified_without_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "original" / "VERIDRA_backup.zip"
    source.parent.mkdir()
    source.write_bytes(b"fixture only - not a real archive")
    destination = tmp_path / "external"
    destination.mkdir()
    monkeypatch.setattr(copy_tool, "_independent_volume", lambda src, dst: True)

    outcome = copy_tool.copy_independent_backup(source, destination)
    assert outcome["status"] == "verified"
    assert outcome["independent_recovery_test"] == "not_yet_performed"
    assert (destination / source.name).read_bytes() == source.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        copy_tool.copy_independent_backup(source, destination)
    assert source.read_bytes() == b"fixture only - not a real archive"


def test_secondary_copy_rejects_same_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "VERIDRA_backup.zip"
    source.write_bytes(b"fixture")
    destination = tmp_path / "second"
    destination.mkdir()
    monkeypatch.setattr(copy_tool, "_independent_volume", lambda src, dst: False)
    with pytest.raises(ValueError, match="separate volume"):
        copy_tool.copy_independent_backup(source, destination)
    assert list(destination.iterdir()) == []


def test_secondary_copy_requires_source_and_destination(tmp_path: Path) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    with pytest.raises(ValueError, match="ZIP backup"):
        copy_tool.copy_independent_backup(tmp_path / "missing.zip", destination)
