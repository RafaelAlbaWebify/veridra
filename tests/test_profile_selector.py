from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import veridra.app as app_module
from veridra.app import app
from veridra.core import Assessment
from veridra.profile_store import ProfileStore
from veridra.report_profiles import ReportProfile

client = TestClient(app)


def _saved_profile(tmp_path: Path) -> str:
    return ProfileStore(tmp_path / "profiles").save(
        ReportProfile(
            organisation_name="Agency <One>",
            client_name="Client A",
            accent_colour="#123456",
        )
    )


def test_selector_lists_and_preserves_saved_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    entry_id = _saved_profile(tmp_path)

    response = client.get("/", params={"demo": "true", "profile": entry_id})

    assert response.status_code == 200
    assert "Agency &lt;One&gt; — Client A" in response.text
    assert f"value='{entry_id}' selected" in response.text
    assert f"/report?demo=true&amp;profile={entry_id}" in response.text
    assert f"/export?demo=true&amp;profile={entry_id}" in response.text
    assert f"name='profile' value='{entry_id}'" in response.text


def test_selected_profile_survives_live_target_and_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    entry_id = _saved_profile(tmp_path)
    expected = Assessment.build("https://example.com", [])
    monkeypatch.setattr(app_module, "assess_url", lambda url: expected)

    response = client.get(
        "/",
        params={
            "url": "example.com",
            "profile": entry_id,
            "area": "Website health",
            "status": "passed",
        },
    )

    assert response.status_code == 200
    assert f"/report?url=example.com&amp;profile={entry_id}" in response.text
    assert f"/export?url=example.com&amp;profile={entry_id}" in response.text
    assert f"profile={entry_id}&amp;area=Website+health" in response.text


def test_unknown_profile_returns_controlled_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))

    response = client.get("/", params={"demo": "true", "profile": "a" * 24})

    assert response.status_code == 404
    assert response.json()["detail"] == "Saved profile was not found."


def test_default_selector_remains_anonymous_and_unbranded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Default Veridra report" in response.text
    assert "/report?demo=true" in response.text
    assert "name='profile' value=" not in response.text
