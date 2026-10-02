from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .crawl_jobs import CrawlJob, CrawlJobState, SQLiteCrawlJobStore
from .identity_tenancy import RequestIdentity, TenantRole
from .tenant_crawl_execution import (
    TenantCrawlExecutionResult,
    execute_tenant_crawl_job,
)
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import UsageEvent, UsageKind

Execution = Callable[..., TenantCrawlExecutionResult]


@dataclass(frozen=True)
class CrawlWorkerResult:
    leased: int
    succeeded: int
    retried: int
    failed: int


def _worker_identity(tenant_id: str, *, now: datetime) -> RequestIdentity:
    return RequestIdentity(
        user_id="0" * 24,
        tenant_id=tenant_id,
        membership_role=TenantRole.owner,
        session_id="0" * 24,
        authenticated_at=now,
    )


def _usage_already_recorded(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
    *,
    kind: UsageKind,
    job_id: str,
) -> bool:
    return any(
        event.kind is kind and event.related_id == job_id
        for _, event in policy.usage_ledger(identity).list()
    )


def _reconcile_usage(
    *,
    root: Path,
    job: CrawlJob,
    result: TenantCrawlExecutionResult,
    now: datetime,
) -> None:
    identity = _worker_identity(job.tenant_id, now=now)
    policy = TenantWorkspacePolicy(root)
    if not policy.workspace_store(identity).path.exists():
        return
    ledger = policy.usage_ledger(identity)

    if not _usage_already_recorded(
        policy,
        identity,
        kind=UsageKind.audit,
        job_id=job.id,
    ):
        if not job.audit_reservation_id:
            raise RuntimeError("Crawl-job audit usage reservation is missing.")
        ledger.record_reserved(
            job.audit_reservation_id,
            UsageEvent(
                kind=UsageKind.audit,
                quantity=1,
                occurred_at=job.created_at,
                related_id=job.id,
                note="Durable crawl job audit",
            ),
        )

    if not _usage_already_recorded(
        policy,
        identity,
        kind=UsageKind.crawled_page,
        job_id=job.id,
    ):
        if not job.page_reservation_id:
            if result.pages_completed == 0:
                return
            raise RuntimeError("Crawl-job page usage reservation is missing.")
        if result.pages_completed == 0:
            ledger.release_reservation(job.page_reservation_id)
        else:
            ledger.record_reserved(
                job.page_reservation_id,
                UsageEvent(
                    kind=UsageKind.crawled_page,
                    quantity=result.pages_completed,
                    occurred_at=job.created_at,
                    related_id=job.id,
                    note="Durable crawl job pages",
                ),
            )


def _release_remaining_reservations(*, root: Path, job: CrawlJob) -> None:
    identity = _worker_identity(job.tenant_id, now=datetime.now(UTC))
    policy = TenantWorkspacePolicy(root)
    if not policy.workspace_store(identity).path.exists():
        return
    ledger = policy.usage_ledger(identity)
    for reservation_id in (
        job.audit_reservation_id,
        job.page_reservation_id,
    ):
        if reservation_id:
            ledger.release_reservation(reservation_id)


class CrawlWorker:
    def __init__(
        self,
        *,
        root: Path,
        store: SQLiteCrawlJobStore | None = None,
        execute: Execution = execute_tenant_crawl_job,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = root
        self.store = store or SQLiteCrawlJobStore(root / "crawl-jobs.sqlite3")
        self.execute = execute
        self.clock = clock or (lambda: datetime.now(UTC))

    def run_once(
        self,
        *,
        limit: int = 5,
        lease_duration: timedelta = timedelta(minutes=15),
        retry_delay: timedelta = timedelta(minutes=5),
    ) -> CrawlWorkerResult:
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50.")
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

            def progress(pages_completed: int) -> None:
                self.store.update_progress(
                    job_id=lease.job.id,
                    worker_token=lease.worker_token,
                    pages_completed=pages_completed,
                    now=self.clock(),
                    lease_duration=lease_duration,
                )

            try:
                current = self.store.load(
                    tenant_id=lease.job.tenant_id,
                    job_id=lease.job.id,
                )
                result = self.execute(
                    root=self.root,
                    job=current,
                    progress=progress,
                )
                current = self.store.record_result(
                    job_id=lease.job.id,
                    worker_token=lease.worker_token,
                    now=self.clock(),
                    pages_completed=result.pages_completed,
                    assessment_id=result.assessment_id,
                )
                _reconcile_usage(
                    root=self.root,
                    job=current,
                    result=result,
                    now=self.clock(),
                )
            except Exception as exc:
                finished = self.store.fail(
                    job_id=lease.job.id,
                    worker_token=lease.worker_token,
                    now=self.clock(),
                    error=str(exc) or exc.__class__.__name__,
                    retry_delay=retry_delay,
                )
                if finished.state is CrawlJobState.failed:
                    _release_remaining_reservations(
                        root=self.root,
                        job=finished,
                    )
                    failed += 1
                else:
                    retried += 1
            else:
                self.store.succeed(
                    job_id=lease.job.id,
                    worker_token=lease.worker_token,
                    now=self.clock(),
                    pages_completed=result.pages_completed,
                    assessment_id=result.assessment_id,
                )
                succeeded += 1

        return CrawlWorkerResult(
            leased=leased,
            succeeded=succeeded,
            retried=retried,
            failed=failed,
        )
