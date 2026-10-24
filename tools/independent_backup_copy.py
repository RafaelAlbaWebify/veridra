"""Safely create and verify an independent second copy of a VERIDRA backup."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _independent_volume(source: Path, destination_dir: Path) -> bool:
    if os.name == "nt":
        return os.path.splitdrive(str(source))[0].casefold() != os.path.splitdrive(
            str(destination_dir)
        )[0].casefold()
    return source.stat().st_dev != destination_dir.stat().st_dev


def copy_independent_backup(source: Path, destination_dir: Path) -> dict[str, object]:
    source = source.expanduser().resolve()
    destination_dir = destination_dir.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".zip":
        raise ValueError("A real VERIDRA ZIP backup source is required.")
    if not source.name.startswith("veridra") and not source.name.startswith("VERIDRA"):
        raise ValueError("Source name must identify a VERIDRA backup.")
    if not destination_dir.is_dir() or destination_dir.is_symlink():
        raise ValueError("The destination must be an existing non-symlink directory.")
    if source.parent == destination_dir:
        raise ValueError("The second copy must be in a different directory.")
    if not _independent_volume(source, destination_dir):
        raise ValueError("Select a separate volume or network share for the second copy.")
    target = destination_dir / source.name
    if target.exists() or target.is_symlink():
        raise ValueError("Destination already exists; refusing to overwrite a backup.")
    original = _digest(source)
    fd, temp_name = tempfile.mkstemp(prefix=".veridra-secondary-", dir=destination_dir)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        if _digest(temporary) != original:
            raise ValueError("Second-copy SHA-256 verification failed.")
        if target.exists():
            raise ValueError("Destination appeared during copy; refusing overwrite.")
        temporary.rename(target)
        if _digest(target) != original:
            target.unlink(missing_ok=True)
            raise ValueError("Published second copy failed integrity verification.")
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "status": "verified",
        "archive_name": target.name,
        "bytes": target.stat().st_size,
        "sha256": original,
        "destination_volume": destination_dir.anchor,
        "independent_recovery_test": "not_yet_performed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = copy_independent_backup(args.source, args.destination_dir)
    except (OSError, ValueError) as exc:
        print(f"SECOND_COPY_FAIL: {exc}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
