from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .monitoring_jobs import MonitoringJobState, SQLiteMonitoringJobStore
from .monitoring_worker import MonitoringWorker, MonitoringWorkerResult
from .project_store import ProjectStore, ProjectStoreError


@dataclass(frozen=True)
class MonitoringServiceTick:
    projects_seen: int
    jobs_enqueued: int
    worker: MonitoringWorkerResult


def _valid_id(value: str) -> bool:
    return len(value) == 24 and all(char in "0123456789abcdef" for char in value)


def enqueue_due_projects(root: Path, *, now: datetime | None = None) -> tuple[int, int]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    jobs = SQLiteMonitoringJobStore(root / "monitoring-jobs.sqlite3")
    projects_seen = 0
    jobs_enqueued = 0
    if not root.exists():
        return projects_seen, jobs_enqueued

    for tenant_directory in sorted(root.iterdir()):
        if not tenant_directory.is_dir() or not _valid_id(tenant_directory.name):
            continue
        tenant_id = tenant_directory.name
        project_store = ProjectStore(tenant_directory / "projects")
        existing_jobs = jobs.list_for_tenant(tenant_id)
        for entry in project_store.list():
            projects_seen += 1
            try:
                project = project_store.load(entry.id)
            except ProjectStoreError:
                continue
            schedule = project.monitoring_schedule
            if schedule.cadence.value == "manual":
                continue

            project_jobs = [job for job in existing_jobs if job.project_id == entry.id]
            if project_jobs and project_jobs[0].state in {
                MonitoringJobState.queued,
                MonitoringJobState.leased,
            }:
                continue
            anchor = project_jobs[0].updated_at if project_jobs else None
            due = schedule.next_due(anchor, now=current)
            if due is None or due > current:
                continue
            run_window = due.astimezone(UTC).replace(second=0, microsecond=0).isoformat()
            before = len(project_jobs)
            jobs.enqueue(
                tenant_id=tenant_id,
                project_id=entry.id,
                run_window=run_window,
                now=current,
            )
            after = len([job for job in jobs.list_for_tenant(tenant_id) if job.project_id == entry.id])
            if after > before:
                jobs_enqueued += 1
    return projects_seen, jobs_enqueued


def run_service_tick(root: Path, *, now: datetime | None = None, limit: int = 10) -> MonitoringServiceTick:
    projects_seen, jobs_enqueued = enqueue_due_projects(root, now=now)
    worker = MonitoringWorker(root=root).run_once(limit=limit)
    return MonitoringServiceTick(
        projects_seen=projects_seen,
        jobs_enqueued=jobs_enqueued,
        worker=worker,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Schedule due project monitoring runs and execute durable monitoring jobs."
    )
    parser.add_argument("--tenant-data-root", type=Path, default=None)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    configured = args.tenant_data_root or os.environ.get("VERIDRA_TENANT_DATA_ROOT")
    if configured is None:
        raise SystemExit(
            "Tenant data root is required via --tenant-data-root or VERIDRA_TENANT_DATA_ROOT."
        )
    if args.interval < 5 or args.interval > 3600:
        raise SystemExit("--interval must be between 5 and 3600 seconds.")
    root = Path(configured).expanduser().resolve()
    while True:
        tick = run_service_tick(root, limit=args.limit)
        print(
            "projects_seen={projects} jobs_enqueued={enqueued} leased={leased} "
            "succeeded={succeeded} retried={retried} failed={failed}".format(
                projects=tick.projects_seen,
                enqueued=tick.jobs_enqueued,
                leased=tick.worker.leased,
                succeeded=tick.worker.succeeded,
                retried=tick.worker.retried,
                failed=tick.worker.failed,
            ),
            flush=True,
        )
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
