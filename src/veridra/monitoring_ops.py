from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from .collector import CollectionError
from .core import Assessment, UnsafeTargetError
from .history import HistoryEntry, HistoryStore
from .project_store import ClientProject, ProjectEntry, ProjectStore, ProjectStoreError
from .service import assess_url

_MAX_BATCH_PROJECTS = 20
AssessmentRunner = Callable[[ClientProject], Assessment]


@dataclass(frozen=True)
class ProjectMonitoringState:
    project_id: str
    project_name: str
    target_url: str
    cadence: str
    last_run: datetime | None
    next_due: datetime | None
    status: str


@dataclass(frozen=True)
class BatchItem:
    project_id: str
    project_name: str
    succeeded: bool
    assessment_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatchOutcome:
    attempted: int
    succeeded: int
    failed: int
    truncated: bool
    items: tuple[BatchItem, ...]


def _same_target(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _last_run(project: ClientProject, entries: list[HistoryEntry]) -> datetime | None:
    for entry in entries:
        if _same_target(entry.target, project.target_url):
            return datetime.fromisoformat(entry.generated_at).astimezone(UTC)
    return None


def _status(next_due: datetime | None, *, now: datetime) -> str:
    if next_due is None:
        return "manual"
    if next_due <= now - timedelta(days=1):
        return "overdue"
    if next_due <= now:
        return "due"
    return "upcoming"


def project_monitoring_states(
    *,
    now: datetime | None = None,
    project_store: ProjectStore | None = None,
    history_store: HistoryStore | None = None,
) -> list[ProjectMonitoringState]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    projects = project_store or ProjectStore()
    history = history_store or HistoryStore()
    history_entries = history.list()
    states: list[ProjectMonitoringState] = []
    for entry in projects.list():
        project = projects.load(entry.id)
        last_run = _last_run(project, history_entries)
        next_due = project.monitoring_schedule.next_due(last_run, now=current)
        states.append(
            ProjectMonitoringState(
                project_id=entry.id,
                project_name=project.name,
                target_url=project.target_url,
                cadence=project.monitoring_schedule.cadence.value,
                last_run=last_run,
                next_due=next_due,
                status=_status(next_due, now=current),
            )
        )
    order = {"overdue": 0, "due": 1, "upcoming": 2, "manual": 3}
    return sorted(
        states,
        key=lambda item: (
            order[item.status],
            item.next_due or datetime.max.replace(tzinfo=UTC),
            item.project_name.lower(),
            item.project_id,
        ),
    )


def _default_runner(project: ClientProject) -> Assessment:
    return assess_url(
        project.target_url,
        crawl_profile=project.resolved_crawl_profile(),
    )


def run_due_projects(
    *,
    now: datetime | None = None,
    max_projects: int = _MAX_BATCH_PROJECTS,
    project_store: ProjectStore | None = None,
    history_store: HistoryStore | None = None,
    runner: AssessmentRunner = _default_runner,
) -> BatchOutcome:
    if not 1 <= max_projects <= _MAX_BATCH_PROJECTS:
        raise ValueError(f"Batch size must be between 1 and {_MAX_BATCH_PROJECTS}.")
    projects = project_store or ProjectStore()
    history = history_store or HistoryStore()
    due_states = [
        item
        for item in project_monitoring_states(
            now=now,
            project_store=projects,
            history_store=history,
        )
        if item.status in {"due", "overdue"}
    ]
    selected = due_states[:max_projects]
    outcomes: list[BatchItem] = []
    for state in selected:
        try:
            project = projects.load(state.project_id)
            assessment = runner(project)
            assessment_id = history.save(assessment)
            outcomes.append(
                BatchItem(
                    project_id=state.project_id,
                    project_name=state.project_name,
                    succeeded=True,
                    assessment_id=assessment_id,
                )
            )
        except (
            ProjectStoreError,
            UnsafeTargetError,
            CollectionError,
            ValueError,
            OSError,
        ) as exc:
            outcomes.append(
                BatchItem(
                    project_id=state.project_id,
                    project_name=state.project_name,
                    succeeded=False,
                    error=str(exc),
                )
            )
    succeeded = sum(item.succeeded for item in outcomes)
    return BatchOutcome(
        attempted=len(outcomes),
        succeeded=succeeded,
        failed=len(outcomes) - succeeded,
        truncated=len(due_states) > len(selected),
        items=tuple(outcomes),
    )
