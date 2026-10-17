from __future__ import annotations

from pathlib import Path

import pytest

from veridra.atomic_file_write import atomic_write


def test_atomic_write_creates_and_replaces_file(tmp_path: Path) -> None:
    path = tmp_path / "new" / "record.json"
    atomic_write(path, b'{"version":1}')
    assert path.read_bytes() == b'{"version":1}'
    atomic_write(path, b'{"version":2}')
    assert path.read_bytes() == b'{"version":2}'


def test_failed_replace_does_not_modify_existing_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "customer.json"
    path.write_bytes(b"accepted customer agreement")

    def deny_replace(_source: Path, _destination: Path) -> None:
        raise OSError("simulated filesystem refusal")

    monkeypatch.setattr(Path, "replace", deny_replace)
    with pytest.raises(OSError, match="simulated filesystem refusal"):
        atomic_write(path, b"replacement")
    assert path.read_bytes() == b"accepted customer agreement"
