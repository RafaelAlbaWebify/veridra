from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veridra.app import app

client = TestClient(app)


def _create_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    created = client.post(
        "/profiles",
        data={
            "organisation_name": "Agency <One>",
            "client_name": "Client A",
            "consultant_name": "Rafael",
            "accent_colour": "#123456",
            "introduction": "Intro <script>alert(1)</script>",
            "call_to_action_label": "Book a review",
            "call_to_action_url": "https://example.com/contact",
            "language": "en",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    location = created.headers["location"]
    return location, location.rsplit("/", 1)[1]


def test_profile_workflow_and_report_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location, entry_id = _create_profile(tmp_path, monkeypatch)

    listing = client.get("/profiles")
    assert listing.status_code == 200
    assert "Agency &lt;One&gt;" in listing.text
    assert f"/profiles/{entry_id}/edit" in listing.text

    detail = client.get(location)
    assert detail.status_code == 200
    assert f"/report?demo=true&amp;profile={entry_id}" in detail.text
    assert "Launch branded assessment" in detail.text
    assert "formaction='/report'" in detail.text
    assert "formaction='/export'" in detail.text
    assert f"name='profile' value='{entry_id}'" in detail.text

    report = client.get("/report", params={"demo": "true", "profile": entry_id})
    assert report.status_code == 200
    assert "Agency &lt;One&gt; assessment report" in report.text
    assert "<script>alert(1)</script>" not in report.text

    exported = client.get("/export", params={"demo": "true", "profile": entry_id})
    assert exported.status_code == 200
    with zipfile.ZipFile(BytesIO(exported.content)) as archive:
        report_html = archive.read("report.html").decode("utf-8")
    assert "Agency &lt;One&gt; assessment report" in report_html

    deleted = client.post(f"/profiles/{entry_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert client.get(location).status_code == 404


def test_profile_can_be_edited_and_redirects_to_new_identifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_location, original_id = _create_profile(tmp_path, monkeypatch)

    edit_page = client.get(f"/profiles/{original_id}/edit")
    assert edit_page.status_code == 200
    assert "Edit report profile" in edit_page.text
    assert "Agency &lt;One&gt;" in edit_page.text

    updated = client.post(
        f"/profiles/{original_id}",
        data={
            "organisation_name": "Updated Agency",
            "client_name": "Updated Client",
            "consultant_name": "Rafael",
            "accent_colour": "#654321",
            "language": "es",
            "show_raw_evidence": "true",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303
    replacement_location = updated.headers["location"]
    replacement_id = replacement_location.rsplit("/", 1)[1]
    assert replacement_id != original_id
    assert client.get(original_location).status_code == 404

    detail = client.get(replacement_location)
    assert detail.status_code == 200
    assert "Updated Agency" in detail.text
    assert "Updated Client" in detail.text
    assert "<strong>Language:</strong> es" in detail.text


def test_unknown_profile_is_not_silently_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    response = client.get(
        "/report",
        params={"demo": "true", "profile": "a" * 24},
    )
    assert response.status_code == 404


def test_invalid_profile_submission_returns_400(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    response = client.post(
        "/profiles",
        data={
            "organisation_name": "Agency",
            "accent_colour": "red",
            "language": "en",
        },
    )
    assert response.status_code == 400
