from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veridra.app import app
from veridra.profile_store import ProfileStore
from veridra.report_profiles import ReportProfile

client = TestClient(app)


def test_project_create_list_detail_edit_and_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    profile_id = ProfileStore(tmp_path / "profiles").save(
        ReportProfile(organisation_name="Agency", client_name="Client A")
    )

    created = client.post(
        "/projects",
        data={
            "name": "Client <Site>",
            "client_label": "Client A",
            "target_url": "example.com/path#fragment",
            "profile_id": profile_id,
        },
        follow_redirects=False,
    )

    assert created.status_code == 303
    location = created.headers["location"]
    entry_id = location.rsplit("/", 1)[1]

    listing = client.get("/projects")
    assert listing.status_code == 200
    assert "Client &lt;Site&gt;" in listing.text
    assert "https://example.com/path" in listing.text
    assert f"profile={profile_id}" in listing.text

    detail = client.get(location)
    assert detail.status_code == 200
    encoded_target = "https%3A%2F%2Fexample.com%2Fpath"
    assert f"/report?url={encoded_target}&amp;profile={profile_id}" in detail.text
    assert f"/export?url={encoded_target}&amp;profile={profile_id}" in detail.text
    assert f"/history/save?url={encoded_target}&amp;profile={profile_id}" in detail.text

    edited = client.post(
        f"/projects/{entry_id}/edit",
        data={
            "name": "Updated site",
            "client_label": "Client B",
            "target_url": "example.org",
            "profile_id": "",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 303
    new_location = edited.headers["location"]
    assert new_location != location
    assert client.get(location).status_code == 404
    assert "Updated site" in client.get(new_location).text

    deleted = client.post(f"{new_location}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert client.get(new_location).status_code == 404


def test_project_rejects_missing_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))

    response = client.post(
        "/projects",
        data={
            "name": "Site",
            "target_url": "example.com",
            "profile_id": "a" * 24,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Selected report profile was not found."


def test_project_rejects_invalid_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))

    response = client.post(
        "/projects",
        data={"name": "Site", "target_url": "ftp://example.com"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid client project."
