from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veridra.core import demo_assessment
from veridra.history import HistoryStore
from veridra.project_store import ClientProject, ProjectStore
from veridra.runtime import app
from veridra.task_store import TaskStatus, TaskStore

client = TestClient(app)


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, str]:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    project = ClientProject.build(name="Client <One>", target_url="example.com")
    project_id = ProjectStore().save(project)
    assessment = demo_assessment()
    assessment_id = HistoryStore().save(assessment)
    finding_id = assessment.findings[0].id
    return project_id, assessment_id, finding_id


def test_create_edit_filter_and_delete_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, assessment_id, finding_id = _fixture(tmp_path, monkeypatch)

    new_page = client.get(
        f"/projects/{project_id}/tasks/new",
        params={"assessment": assessment_id, "finding": finding_id},
    )
    assert new_page.status_code == 200
    assert "Create remediation task" in new_page.text

    created = client.post(
        f"/projects/{project_id}/tasks",
        data={
            "finding_id": finding_id,
            "title": "Repair & verify",
            "status": TaskStatus.open.value,
            "notes": "Evidence <required>",
            "owner_label": "Rafael <admin>",
            "due_date": "2026-08-01",
            "source_assessment_id": assessment_id,
        },
        follow_redirects=False,
    )
    assert created.status_code == 303

    tasks = TaskStore().list(project_id=project_id)
    assert len(tasks) == 1
    task_id, task = tasks[0]
    assert task.title == "Repair & verify"

    listed = client.get(f"/projects/{project_id}/tasks")
    assert listed.status_code == 200
    assert "Repair &amp; verify" in listed.text
    assert "Rafael &lt;admin&gt;" in listed.text
    assert "Evidence &lt;required&gt;" not in listed.text

    edited = client.post(
        f"/projects/{project_id}/tasks/{task_id}/edit",
        data={
            "finding_id": finding_id,
            "title": "Repair and verify",
            "status": TaskStatus.verification_required.value,
            "notes": "Ready for another scan",
            "owner_label": "Rafael",
            "due_date": "2026-08-02",
            "source_assessment_id": assessment_id,
        },
        follow_redirects=False,
    )
    assert edited.status_code == 303

    filtered = client.get(
        f"/projects/{project_id}/tasks",
        params={"status": TaskStatus.verification_required.value},
    )
    assert filtered.status_code == 200
    assert "Repair and verify" in filtered.text

    updated_id, _ = TaskStore().list(project_id=project_id)[0]
    deleted = client.post(
        f"/projects/{project_id}/tasks/{updated_id}/delete",
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert TaskStore().list(project_id=project_id) == []


def test_task_routes_reject_invalid_sources_and_cross_project_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, assessment_id, finding_id = _fixture(tmp_path, monkeypatch)
    second = ProjectStore().save(
        ClientProject.build(name="Second", target_url="example.org")
    )

    invalid = client.post(
        f"/projects/{project_id}/tasks",
        data={
            "finding_id": "missing.finding",
            "title": "Invalid",
            "status": TaskStatus.open.value,
            "notes": "",
            "owner_label": "",
            "due_date": "",
            "source_assessment_id": assessment_id,
        },
    )
    assert invalid.status_code == 400

    valid = client.post(
        f"/projects/{project_id}/tasks",
        data={
            "finding_id": finding_id,
            "title": "Valid task",
            "status": TaskStatus.open.value,
            "notes": "",
            "owner_label": "",
            "due_date": "",
            "source_assessment_id": assessment_id,
        },
        follow_redirects=False,
    )
    assert valid.status_code == 303
    task_id, _ = TaskStore().list(project_id=project_id)[0]

    wrong_project = client.get(f"/projects/{second}/tasks/{task_id}/edit")
    assert wrong_project.status_code == 404

    unknown_status = client.get(
        f"/projects/{project_id}/tasks", params={"status": "invented"}
    )
    assert unknown_status.status_code == 400
