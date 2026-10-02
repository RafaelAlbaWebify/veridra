from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from veridra.crawl_jobs import (
    CrawlJobError,
    CrawlJobState,
    SQLiteCrawlJobStore,
)

NOW = datetime(2026, 10, 2, 11, 45, tzinfo=UTC)
TENANT_A = "a" * 24
TENANT_B = "b" * 24
PROJECT_A = "c" * 24
PROJECT_B = "d" * 24


def _store(tmp_path: Path) -> SQLiteCrawlJobStore:
    store = SQLiteCrawlJobStore(tmp_path / "crawl-jobs.sqlite3")
    store.initialize()
    return store


def _enqueue(
    store: SQLiteCrawlJobStore,
    *,
    tenant_id: str = TENANT_A,
    project_id: str = PROJECT_A,
    request_key: str = "manual:1",
    max_active_for_tenant: int = 1,
) -> object:
    return store.enqueue(
        tenant_id=tenant_id,
        project_id=project_id,
        target_url="https://example.com/",
        crawl_profile="deep",
        page_budget=100,
        request_key=request_key,
        now=NOW,
        max_active_for_tenant=max_active_for_tenant,
    )


def test_enqueue_is_idempotent_before_concurrency_check(tmp_path: Path) -> None:
    store = _store(tmp_path)

    first = _enqueue(store)
    second = _enqueue(store)

    assert second == first
    assert store.list_for_tenant(TENANT_A) == (first,)


def test_active_job_concurrency_is_tenant_scoped(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _enqueue(store)

    with pytest.raises(CrawlJobError, match="concurrency allowance"):
        _enqueue(
            store,
            project_id=PROJECT_B,
            request_key="manual:2",
            max_active_for_tenant=1,
        )

    other = _enqueue(
        store,
        tenant_id=TENANT_B,
        project_id=PROJECT_B,
        request_key="manual:2",
        max_active_for_tenant=1,
    )

    assert first.tenant_id == TENANT_A
    assert other.tenant_id == TENANT_B


def test_only_one_worker_can_lease_due_crawl_job(tmp_path: Path) -> None:
    store = _store(tmp_path)
    queued = _enqueue(store)

    first = store.lease_next(now=NOW, lease_duration=timedelta(minutes=15))
    second = store.lease_next(now=NOW, lease_duration=timedelta(minutes=15))

    assert first is not None
    assert first.job.id == queued.id
    assert first.job.state is CrawlJobState.leased
    assert second is None


def test_expired_lease_can_be_recovered(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _enqueue(store)
    first = store.lease_next(now=NOW, lease_duration=timedelta(minutes=5))
    assert first is not None

    recovered = store.lease_next(
        now=NOW + timedelta(minutes=6),
        lease_duration=timedelta(minutes=5),
    )

    assert recovered is not None
    assert recovered.job.id == first.job.id
    assert recovered.worker_token != first.worker_token
    with pytest.raises(CrawlJobError, match="lease was not found"):
        store.update_progress(
            job_id=first.job.id,
            worker_token=first.worker_token,
            pages_completed=10,
            now=NOW + timedelta(minutes=7),
        )


def test_progress_is_lease_bound_and_cannot_exceed_page_budget(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _enqueue(store)
    lease = store.lease_next(now=NOW, lease_duration=timedelta(minutes=15))
    assert lease is not None

    updated = store.update_progress(
        job_id=lease.job.id,
        worker_token=lease.worker_token,
        pages_completed=37,
        now=NOW + timedelta(minutes=1),
    )

    assert updated.pages_completed == 37
    assert updated.page_budget == 100
    with pytest.raises(CrawlJobError, match="reserved page budget"):
        store.update_progress(
            job_id=lease.job.id,
            worker_token=lease.worker_token,
            pages_completed=101,
            now=NOW + timedelta(minutes=2),
        )


def test_success_records_assessment_and_releases_concurrency_slot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _enqueue(store)
    lease = store.lease_next(now=NOW, lease_duration=timedelta(minutes=15))
    assert lease is not None

    succeeded = store.succeed(
        job_id=lease.job.id,
        worker_token=lease.worker_token,
        now=NOW + timedelta(minutes=2),
        pages_completed=82,
        assessment_id="e" * 24,
    )

    assert succeeded.state is CrawlJobState.succeeded
    assert succeeded.pages_completed == 82
    assert succeeded.assessment_id == "e" * 24
    assert succeeded.attempt_count == 1

    next_job = _enqueue(
        store,
        project_id=PROJECT_B,
        request_key="manual:2",
        max_active_for_tenant=1,
    )
    assert next_job.state is CrawlJobState.queued


def test_failure_requeues_then_becomes_terminal(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT_A,
        target_url="https://example.com/",
        crawl_profile="deep",
        page_budget=100,
        request_key="manual:1",
        now=NOW,
        max_attempts=2,
        max_active_for_tenant=1,
    )
    first = store.lease_next(now=NOW, lease_duration=timedelta(minutes=5))
    assert first is not None

    queued = store.fail(
        job_id=first.job.id,
        worker_token=first.worker_token,
        now=NOW + timedelta(minutes=1),
        error="temporary network failure",
        retry_delay=timedelta(minutes=10),
    )

    assert queued.state is CrawlJobState.queued
    assert queued.attempt_count == 1
    assert queued.last_error == "temporary network failure"
    assert store.lease_next(
        now=NOW + timedelta(minutes=10),
        lease_duration=timedelta(minutes=5),
    ) is None

    second = store.lease_next(
        now=NOW + timedelta(minutes=11),
        lease_duration=timedelta(minutes=5),
    )
    assert second is not None
    failed = store.fail(
        job_id=second.job.id,
        worker_token=second.worker_token,
        now=NOW + timedelta(minutes=12),
        error="still failing",
        retry_delay=timedelta(minutes=10),
    )

    assert failed.state is CrawlJobState.failed
    assert failed.attempt_count == 2
    assert failed.last_error == "still failing"


def test_cancel_is_tenant_qualified_and_terminal(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = _enqueue(store)

    with pytest.raises(CrawlJobError, match="not found"):
        store.cancel(tenant_id=TENANT_B, job_id=job.id, now=NOW)

    cancelled = store.cancel(
        tenant_id=TENANT_A,
        job_id=job.id,
        now=NOW,
    )

    assert cancelled.state is CrawlJobState.cancelled
    assert store.lease_next(
        now=NOW,
        lease_duration=timedelta(minutes=5),
    ) is None


def test_invalid_identifiers_fail_before_storage(tmp_path: Path) -> None:
    store = SQLiteCrawlJobStore(tmp_path / "crawl-jobs.sqlite3")

    with pytest.raises(CrawlJobError, match="tenant_id"):
        store.enqueue(
            tenant_id="../outside",
            project_id=PROJECT_A,
            target_url="https://example.com/",
            crawl_profile="deep",
            page_budget=100,
            request_key="manual:1",
            now=NOW,
        )

    assert not store.database.exists()
