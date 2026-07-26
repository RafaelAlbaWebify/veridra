from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .monitoring_jobs import MonitoringJobState, SQLiteMonitoringJobStore
from .tenant_monitoring_execution import (
    TenantMonitoringExecutionResult,
    execute_tenant_monitoring,
)

Execution = Callable[..., TenantMonitoringExecutionResult]


@dataclass(frozen=True)
class MonitoringWorkerResult:
    leased: int
    succeeded: int
    retried: int
    failed: int


class MonitoringWorker:
    def __init__(
        self,
        *,
        root: Path,
        store: SQLiteMonitoringJobStore | None = None,
        execute: Execution = execute_tenant_monitoring,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = root
        self.store = store or SQLiteMonitoringJobStore(root / "monitoring-jobs.sqlite3")
        self.execute = execute
        self.clock = clock or (lambda: datetime.now(UTC))

    def run_once(
        self,
        *,
        limit: int = 10,
        lease_duration: timedelta = timedelta(minutes=15),
        retry_delay: timedelta = timedelta(minutes=5),
    ) -> MonitoringWorkerResult:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100.")
        leased = 0
        succeeded = 0
        retried = 0
        failed = 0
        for _ in range(limit):
            lease = self.store.lease_next(
                now=self.clock(),
                lease_duration=lease_duration,
            )
            if lease is None:
                break
            leased += 1
            try:
                self.execute(
                    root=self.root,
                    tenant_id=lease.job.tenant_id,
                    project_id=lease.job.project_id,
                )
            except Exception as exc:
                finished = self.store.fail(
                    job_id=lease.job.id,
                    worker_token=lease.worker_token,
                    now=self.clock(),
                    error=str(exc) or exc.__class__.__name__,
                    retry_delay=retry_delay,
                )
                if finished.state is MonitoringJobState.failed:
                    failed += 1
                else:
                    retried += 1
            else:
                self.store.succeed(
                    job_id=lease.job.id,
                    worker_token=lease.worker_token,
                    now=self.clock(),
                )
                succeeded += 1
        return MonitoringWorkerResult(
            leased=leased,
            succeeded=succeeded,
            retried=retried,
            failed=failed,
        )
