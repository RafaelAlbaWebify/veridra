from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from veridra.monitoring_ops import BatchOutcome
from veridra.project_store import ClientProject, ProjectStore
from veridra.runtime import app


def _project(tmp_path: Path, monkeypatch: MonkeyPatch) -> tuple[str, ProjectStore]:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    store = ProjectStore()
    entry_id = store.save(
        ClientProject.build(
            name="Example client",
            target_url="https://example.com",
        )
    )
    return entry_id, store


def test_monitoring_dashboard_lists_saved_project(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _project(tmp_path, monkeypatch)
    response = TestClient(app).get("/monitoring")
    assert response.status_code == 200
    assert "Monitoring operations" in response.text
    assert "Example client" in response.text
    assert "Schedules are evaluated only while Veridra is running" in response.text


def test_schedule_editor_updates_project_atomically(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    entry_id, store = _project(tmp_path, monkeypatch)
    response = TestClient(app).post(
        f"/monitoring/projects/{entry_id}/schedule",
        data={
            "cadence": "weekly",
            "timezone": "Europe/Madrid",
            "hour": "9",
            "minute": "30",
            "weekday": "1",
            "day_of_month": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    replacement_id = response.headers["location"].split("/")[-2]
    project = store.load(replacement_id)
    assert project.monitoring_schedule.cadence.value == "weekly"
    assert project.monitoring_schedule.timezone == "Europe/Madrid"
    assert project.monitoring_schedule.weekday == 1


def test_invalid_schedule_is_rejected(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    entry_id, _ = _project(tmp_path, monkeypatch)
    response = TestClient(app).post(
        f"/monitoring/projects/{entry_id}/schedule",
        data={
            "cadence": "weekly",
            "timezone": "Invalid/Timezone",
            "hour": "9",
            "minute": "0",
            "weekday": "1",
            "day_of_month": "",
        },
    )
    assert response.status_code == 400


def test_run_due_redirects_with_batch_summary(monkeypatch: MonkeyPatch) -> None:
    from veridra import monitoring_web

    monkeypatch.setattr(
        monitoring_web,
        "run_due_projects",
        lambda: BatchOutcome(
            attempted=2,
            succeeded=1,
            failed=1,
            truncated=True,
            items=(),
        ),
    )
    response = TestClient(app).post("/monitoring/run-due", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == (
        "/monitoring?succeeded=1&failed=1&truncated=true"
    )
