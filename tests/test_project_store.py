from __future__ import annotations

from pathlib import Path

import pytest

from veridra.project_store import (
    ClientProject,
    ProjectStore,
    ProjectStoreError,
    project_id,
)


def test_project_store_round_trip_and_delete(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = ClientProject.build(
        name="Client site",
        target_url="example.com/path#fragment",
        client_label="Client A",
        profile_id="a" * 24,
    )

    entry_id = store.save(project)

    assert entry_id == project_id(project)
    assert store.load(entry_id) == project
    assert store.list()[0].target_url == "https://example.com/path"
    assert not list(tmp_path.glob("*.tmp"))

    store.delete(entry_id)
    assert store.list() == []


def test_project_replace_changes_identifier_and_removes_old_file(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    original = ClientProject.build(name="Original", target_url="example.com")
    original_id = store.save(original)

    replacement = ClientProject.build(name="Updated", target_url="example.org")
    replacement_id = store.replace(original_id, replacement)

    assert replacement_id != original_id
    assert store.load(replacement_id) == replacement
    with pytest.raises(ProjectStoreError, match="not found"):
        store.load(original_id)


def test_project_store_rejects_invalid_identifier(tmp_path: Path) -> None:
    with pytest.raises(ProjectStoreError, match="Invalid project identifier"):
        ProjectStore(tmp_path).load("../unsafe")


def test_project_normalizes_and_rejects_unsupported_target() -> None:
    assert ClientProject.build(name="Site", target_url="example.com").target_url == (
        "https://example.com"
    )

    with pytest.raises(ValueError, match="Only HTTP and HTTPS"):
        ClientProject.build(name="Site", target_url="ftp://example.com")
