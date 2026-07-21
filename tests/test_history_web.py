from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veridra.app import app

client = TestClient(app)


def _configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))


def test_history_starts_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    response = client.get("/history")
    assert response.status_code == 200
    assert "No assessments have been explicitly saved" in response.text
    assert "Local operator-controlled storage only" in response.text


def test_demo_save_detail_and_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    saved = client.post("/history/save", params={"demo": "true"}, follow_redirects=False)
    assert saved.status_code == 303
    location = saved.headers["location"]
    entry_id = location.rsplit("/", 1)[1]

    detail = client.get(location)
    assert detail.status_code == 200
    assert "demo.veridra.local" in detail.text
    assert entry_id in detail.text

    listing = client.get("/history")
    assert entry_id in listing.text

    deleted = client.post(f"/history/{entry_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert client.get("/history").text.count(entry_id) == 0


def test_comparison_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    first = client.post("/history/save", params={"demo": "true"}, follow_redirects=False)
    first_id = first.headers["location"].rsplit("/", 1)[1]

    history_file = tmp_path / "history" / f"{first_id}.json"
    content = history_file.read_text(encoding="utf-8")
    changed = content.replace('"elapsed_ms":0', '"elapsed_ms":1')
    second_file = tmp_path / "history" / ("f" * 24 + ".json")
    second_file.write_text(changed, encoding="utf-8")

    response = client.get(
        "/history/compare",
        params={"before": first_id, "after": "f" * 24},
    )
    assert response.status_code == 200
    assert "Assessment comparison" in response.text
    assert "Unchanged findings" in response.text


def test_retention_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    client.post("/history/save", params={"demo": "true"})
    response = client.post("/history/prune", params={"keep": 0}, follow_redirects=False)
    assert response.status_code == 303
    assert "No assessments have been explicitly saved" in client.get("/history").text


def test_invalid_history_identifier_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    response = client.get("/history/not-valid")
    assert response.status_code == 404
