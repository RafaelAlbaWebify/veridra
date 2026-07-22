from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.core import Assessment, demo_assessment
from veridra.history import HistoryStore
from veridra.monitoring_ops import project_monitoring_states, run_due_projects
from veridra.monitoring_schedule import MonitoringSchedule
from veridra.project_store import ClientProject, ProjectStore


def _stores(tmp_path: Path) -> tuple[ProjectStore, HistoryStore]:
    return (
        ProjectStore(tmp_path / "projects"),
        HistoryStore(tmp_path / "history"),
    )


def test_manual_and_due_projects_are_classified(tmp_path: Path) -> None:
    projects, history = _stores(tmp_path)
    projects.save(ClientProject.build(name="Manual", target_url="https://manual.example"))
    projects.save(
        ClientProject.build(
            name="Daily",
            target_url="https://daily.example",
            monitoring_schedule=MonitoringSchedule(cadence="daily", timezone="UTC"),
        )
    )
    states = project_monitoring_states(
        now=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        project_store=projects,
        history_store=history,
    )
    assert [(item.project_name, item.status) for item in states] == [
        ("Daily", "due"),
        ("Manual", "manual"),
    ]


def test_recent_daily_assessment_is_upcoming(tmp_path: Path) -> None:
    projects, history = _stores(tmp_path)
    projects.save(
        ClientProject.build(
            name="Daily",
            target_url="https://example.com",
            monitoring_schedule=MonitoringSchedule(
                cadence="daily",
                timezone="UTC",
                hour=9,
            ),
        )
    )
    assessment = demo_assessment().model_copy(
        update={
            "target": "https://example.com/",
            "generated_at": datetime(2026, 7, 22, 9, 30, tzinfo=UTC),
        }
    )
    history.save(Assessment.model_validate(assessment))
    states = project_monitoring_states(
        now=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        project_store=projects,
        history_store=history,
    )
    assert states[0].status == "upcoming"
    assert states[0].next_due == datetime(2026, 7, 23, 9, 0, tzinfo=UTC)


def test_batch_is_bounded_and_isolates_failures(tmp_path: Path) -> None:
    projects, history = _stores(tmp_path)
    for name in ("A", "B", "C"):
        projects.save(
            ClientProject.build(
                name=name,
                target_url=f"https://{name.lower()}.example",
                monitoring_schedule=MonitoringSchedule(cadence="daily", timezone="UTC"),
            )
        )

    def runner(project: ClientProject) -> Assessment:
        if project.name == "B":
            raise ValueError("simulated failure")
        return demo_assessment().model_copy(update={"target": project.target_url})

    outcome = run_due_projects(
        now=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        max_projects=3,
        project_store=projects,
        history_store=history,
        runner=runner,
    )
    assert outcome.attempted == 3
    assert outcome.succeeded == 2
    assert outcome.failed == 1
    assert any(item.error == "simulated failure" for item in outcome.items)
    assert len(history.list()) == 2


def test_batch_limit_is_enforced(tmp_path: Path) -> None:
    projects, history = _stores(tmp_path)
    with pytest.raises(ValueError, match="Batch size"):
        run_due_projects(
            max_projects=21,
            project_store=projects,
            history_store=history,
        )
