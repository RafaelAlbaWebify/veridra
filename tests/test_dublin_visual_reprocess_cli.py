from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from veridra.dublin_visual_reprocess_cli import extract_audit_zip, latest_dublin_batch


def test_latest_dublin_batch_prefers_newest(tmp_path: Path) -> None:
    older = tmp_path / "VERIDRA_DUBLIN_BATCH_20260824_100000.zip"
    newer = tmp_path / "VERIDRA_DUBLIN_BATCH_20260824_110000.zip"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    older.touch()
    newer.touch()
    older_mtime = older.stat().st_mtime
    newer_mtime = newer.stat().st_mtime
    if newer_mtime <= older_mtime:
        import os

        os.utime(newer, (older_mtime + 10, older_mtime + 10))
    assert latest_dublin_batch(tmp_path) == newer


def test_extract_audit_zip_reads_nested_stage(tmp_path: Path) -> None:
    batch = tmp_path / "VERIDRA_DUBLIN_BATCH_20260824_193555.zip"
    output = tmp_path / "audit.zip"
    with zipfile.ZipFile(batch, "w") as archive:
        archive.writestr("02-audits.zip", b"audit payload")
    extract_audit_zip(batch, output)
    assert output.read_bytes() == b"audit payload"


def test_extract_audit_zip_requires_stage(tmp_path: Path) -> None:
    batch = tmp_path / "VERIDRA_DUBLIN_BATCH_20260824_193555.zip"
    with zipfile.ZipFile(batch, "w") as archive:
        archive.writestr("batch_manifest.json", "{}")
    with pytest.raises(ValueError, match="02-audits.zip"):
        extract_audit_zip(batch, tmp_path / "audit.zip")
