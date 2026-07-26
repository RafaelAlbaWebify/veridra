from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from veridra.monitoring_jobs import (
    MonitoringJobError,
    MonitoringJobState,
    SQLiteMonitoringJobStore,
)

NOW = datetime(2026, 7, 26, 16, 0, tzinfo=UTC)
TENANT_A = "a" * 24
TENANT_B = "b" * 24
PROJECT = "c" * 24


def _store(tmp_path: Path) -> SQLiteMonitoringJobStore:
    store = SQLiteMonitoringJobStore(tmp_path / "monitoring-jobs.sqlite3")
    store.initialize()
    return store


def test_enqueue_is_idempotent_for_tenant_project_and_window(tmp_path: Path) -> None:
    store = _store(tmp_path)

    first = store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT,
        run_window="2026-07-26T16:00Z",
        now=NOW,
    )
    second = store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT,
        run_window="2026-07-26T16:00Z",
        now=NOW + timedelta(minutes=1),
    )

    assert second == first
    assert store.list_for_tenant(TENANT_A) == (first,)


def test_identical_project_and_window_are_isolated_by_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path)

    first = store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT,
        run_window="daily:2026-07-26",
        now=NOW,
    )
    second = store.enqueue(
        tenant_id=TENANT_B,
        project_id=PROJECT,
        run_window="daily:2026-07-26",
        now=NOW,
    )

    assert first.id != second.id
    assert store.list_for_tenant(TENANT_A) == (first,)
    assert store.list_for_tenant(TENANT_B) == (second,)
    with pytest.raises(MonitoringJobError, match="not found"):
        store.load(tenant_id=TENANT_A, job_id=second.id)


def test_only_one_worker_can_lease_a_due_job(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT,
        run_window="hourly:2026-07-26T16",
        now=NOW,
    )

    first = store.lease_next(now=NOW, lease_duration=timedelta(minutes=5))
    second = store.lease_next(now=NOW, lease_duration=timedelta(minutes=5))

    assert first is not None
    assert first.job.id == job.id
    assert first.job.state is MonitoringJobState.leased
    assert second is None


def test_expired_lease_can_be_recovered_by_another_worker(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT,
        run_window="hourly:2026-07-26T16",
        now=NOW,
    )
    first = store.lease_next(now=NOW, lease_duration=timedelta(minutes=5))
    assert first is not None

    recovered = store.lease_next(
        now=NOW + timedelta(minutes=6),
        lease_duration=timedelta(minutes=5),
    )

    assert recovered is not None
    assert recovered.job.id == first.job.id
    assert recovered.worker_token != first.worker_token
    with pytest.raises(MonitoringJobError, match="lease was not found"):
        store.succeed(
            job_id=first.job.id,
            worker_token=first.worker_token,
            now=NOW + timedelta(minutes=7),
        )


def test_success_is_terminal_and_cannot_be_repeated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT,
        run_window="daily:2026-07-26",
        now=NOW,
    )
    lease = store.lease_next(now=NOW, lease_duration=timedelta(minutes=5))
    assert lease is not None

    succeeded = store.succeed(
        job_id=lease.job.id,
        worker_token=lease.worker_token,
        now=NOW + timedelta(minutes=1),
    )

    assert succeeded.state is MonitoringJobState.succeeded
    assert succeeded.attempt_count == 1
    assert store.lease_next(
        now=NOW + timedelta(hours=1),
        lease_duration=timedelta(minutes=5),
    ) is None
    with pytest.raises(MonitoringJobError, match="lease was not found"):
        store.succeed(
            job_id=lease.job.id,
            worker_token=lease.worker_token,
            now=NOW + timedelta(minutes=2),
        )


def test_failure_requeues_then_becomes_terminal_at_retry_limit(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT,
        run_window="daily:2026-07-26",
        now=NOW,
        max_attempts=2,
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

    assert queued.state is MonitoringJobState.queued
    assert queued.attempt_count == 1
    assert queued.last_error == "temporary network failure"
    assert queued.next_attempt_at == NOW + timedelta(minutes=11)
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

    assert failed.state is MonitoringJobState.failed
    assert failed.attempt_count == 2
    assert failed.last_error == "still failing"
    assert store.lease_next(
        now=NOW + timedelta(days=1),
        lease_duration=timedelta(minutes=5),
    ) is None


def test_cancellation_is_tenant_qualified_and_prevents_leasing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = store.enqueue(
        tenant_id=TENANT_A,
        project_id=PROJECT,
        run_window="daily:2026-07-26",
        now=NOW,
    )

    with pytest.raises(MonitoringJobError, match="not found"):
        store.cancel(tenant_id=TENANT_B, job_id=job.id, now=NOW)

    cancelled = store.cancel(tenant_id=TENANT_A, job_id=job.id, now=NOW)

    assert cancelled.state is MonitoringJobState.cancelled
    assert store.lease_next(now=NOW, lease_duration=timedelta(minutes=5)) is None


def test_invalid_identifiers_are_rejected_before_storage(tmp_path: Path) -> None:
    store = SQLiteMonitoringJobStore(tmp_path / "monitoring-jobs.sqlite3")

    with pytest.raises(MonitoringJobError, match="tenant_id"):
        store.enqueue(
            tenant_id="../outside",
            project_id=PROJECT,
            run_window="daily:2026-07-26",
            now=NOW,
        )

    assert not store.database.exists()
