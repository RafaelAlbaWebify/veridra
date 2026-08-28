from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.monitoring_jobs import SQLiteMonitoringJobStore
from veridra.monitoring_schedule import MonitoringCadence, MonitoringSchedule
from veridra.monitoring_service import enqueue_due_projects
from veridra.project_store import ClientProject, ProjectStore

TENANT_ID = "a" * 24
NOW = datetime(2026, 8, 28, 16, 0, tzinfo=UTC)


def _scheduled_project(root: Path) -> tuple[Path, str]:
    tenant_root = root / TENANT_ID
    store = ProjectStore(tenant_root / "projects")
    project = ClientProject.build(
        name="Scheduled client",
        target_url="https://example.com",
    ).model_copy(
        update={
            "monitoring_schedule": MonitoringSchedule(
                cadence=MonitoringCadence.weekly,
                timezone="Europe/Madrid",
                hour=9,
                minute=0,
                weekday=0,
            )
        }
    )
    project_id = store.save(project)
    return tenant_root, project_id


def test_due_schedule_enqueues_one_idempotent_job(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    _, project_id = _scheduled_project(root)

    first = enqueue_due_projects(root, now=NOW)
    second = enqueue_due_projects(root, now=NOW)

    assert first == (1, 1)
    assert second == (1, 0)
    jobs = SQLiteMonitoringJobStore(root / "monitoring-jobs.sqlite3").list_for_tenant(TENANT_ID)
    assert len(jobs) == 1
    assert jobs[0].project_id == project_id
    assert jobs[0].run_window == NOW.replace(second=0, microsecond=0).isoformat()


def test_manual_project_does_not_enqueue(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    tenant_root = root / TENANT_ID
    ProjectStore(tenant_root / "projects").save(
        ClientProject.build(name="Manual client", target_url="https://example.com")
    )

    result = enqueue_due_projects(root, now=NOW)

    assert result == (1, 0)
    jobs = SQLiteMonitoringJobStore(root / "monitoring-jobs.sqlite3").list_for_tenant(TENANT_ID)
    assert jobs == ()
