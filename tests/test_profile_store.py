from __future__ import annotations

from pathlib import Path

import pytest

from veridra.profile_store import ProfileStore, ProfileStoreError, profile_id
from veridra.report_profiles import ReportProfile


def test_profile_store_saves_loads_lists_and_deletes(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path)
    profile = ReportProfile(
        organisation_name="Agency One",
        client_name="Client A",
        consultant_name="Consultant",
        accent_colour="#123456",
        show_raw_evidence=False,
    )

    entry_id = store.save(profile)

    assert entry_id == profile_id(profile)
    assert store.load(entry_id) == profile
    assert store.list()[0].organisation_name == "Agency One"
    assert not list(tmp_path.glob("*.tmp"))

    store.delete(entry_id)
    assert store.list() == []


def test_profile_store_overwrites_same_identifier_atomically(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path)
    profile = ReportProfile(organisation_name="Stable Agency")

    first = store.save(profile)
    second = store.save(profile)

    assert first == second
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_profile_store_rejects_invalid_identifier(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path)

    with pytest.raises(ProfileStoreError, match="Invalid profile identifier"):
        store.load("../unsafe")
