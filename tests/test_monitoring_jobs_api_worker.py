from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from veridra.monitoring_job_store import MonitoringJobState, SQLiteMonitoringJobStore

from veridra.identity_middleware import VerifiedIdentityMiddleware
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.monitoring_job_api import router as monitoring_job_router
from veridra.monitoring_worker import MonitoringWorker
from veridra.project_store import ClientProject
from veridra.tenant_monitoring_execution import TenantMonitoringExecutionResult
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 26, 16, 0, tzinfo=UTC)
TENANT_A = "a" * 24
TENANT_B = "b" * 24


class StaticAdapter:
    def __init__(self, identity: RequestIdentity) -> None:
        self.identity = identity

    async def resolve(self, request: object) -> RequestIdentity:
        del request
        return self.identity


def _identity(tenant_id: str, role: TenantRole = TenantRole.analyst) -> RequestIdentity:
    return RequestIdentity(
        user_id="c" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="session-identifier-value-01",
        authenticated_at=NOW,
    )


def _project(root: Path, identity: RequestIdentity) -> str:
    return TenantProjectStore(root).save(
        identity,
        ClientProject.build(name="Monitored", target_url="https://example.com"),
    )


def _client(root: Path, identity: RequestIdentity) -> TestClient:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    app.add_middleware(VerifiedIdentityMiddleware, adapter=StaticAdapter(identity))
    app.include_router(monitoring_job_router)
    return TestClient(app)


def test_authenticated_job_api_is_tenant_qualified(tmp_path: Path) -> None:
    analyst_a = _identity(TENANT_A)
    analyst_b = _identity(TENANT_B)
    project_a = _project(tmp_path, analyst_a)
    project_b = _project(tmp_path, analyst_b)
    client_a = _client(tmp_path, analyst_a)

    created = client_a.post(
        "/api/tenant/monitoring-jobs",
        json={"project_id": project_a, "run_window": "2026-07-27T08:00Z"},
    )
    duplicate = client_a.post(
        "/api/tenant/monitoring-jobs",
        json={"project_id": project_a, "run_window": "2026-07-27T08:00Z"},
    )
    concealed = client_a.post(
        "/api/tenant/monitoring-jobs",
        json={"project_id": project_b, "run_window": "2026-07-27T08:00Z"},
    )
    listed = client_a.get("/api/tenant/monitoring-jobs")

    assert created.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == created.json()["id"]
    assert concealed.status_code == 404
    assert len(listed.json()) == 1


def test_viewer_can_list_but_cannot_enqueue_or_cancel(tmp_path: Path) -> None:
    analyst = _identity(TENANT_A)
    project_id = _project(tmp_path, analyst)
    viewer = _identity(TENANT_A, TenantRole.viewer)
    viewer_client = _client(tmp_path, viewer)
    store = SQLiteMonitoringJobStore(tmp_path / "monitoring-jobs.sqlite3")
    job = store.enqueue(
        tenant_id=TENANT_A,
        project_id=project_id,
        run_window="window",
        now=NOW,
    )

    assert viewer_client.get("/api/tenant/monitoring-jobs").status_code == 200
    assert viewer_client.post(
        "/api/tenant/monitoring-jobs",
        json={"project_id": project_id, "run_window": "other"},
    ).status_code == 403
    assert viewer_client.delete(f"/api/tenant/monitoring-jobs/{job.id}").status_code == 403


def test_worker_executes_bounded_jobs_and_records_success(tmp_path: Path) -> None:
    store = SQLiteMonitoringJobStore(tmp_path / "monitoring-jobs.sqlite3")
    for index in range(3):
        store.enqueue(
            tenant_id=TENANT_A,
            project_id=f"{index + 1:024x}",
            run_window=f"window-{index}",
            now=NOW,
        )
    calls: list[tuple[str, str]] = []

    def execute(
        *, root: Path, tenant_id: str, project_id: str
    ) -> TenantMonitoringExecutionResult:
        assert root == tmp_path
        calls.append((tenant_id, project_id))
        return TenantMonitoringExecutionResult(
            assessment_id="d" * 24,
            email_status=None,
            email_error=None,
        )

    result = MonitoringWorker(
        root=tmp_path,
        store=store,
        execute=execute,
        clock=lambda: NOW,
    ).run_once(limit=2)

    assert result.leased == 2
    assert result.succeeded == 2
    assert len(calls) == 2
    states = [job.state for job in store.list_for_tenant(TENANT_A)]
    assert states.count(MonitoringJobState.succeeded) == 2
    assert states.count(MonitoringJobState.queued) == 1


def test_worker_retries_then_marks_terminal_failure(tmp_path: Path) -> None:
    store = SQLiteMonitoringJobStore(tmp_path / "monitoring-jobs.sqlite3")
    job = store.enqueue(
        tenant_id=TENANT_A,
        project_id="1" * 24,
        run_window="window",
        now=NOW,
        max_attempts=2,
    )

    def fail_execution(
        *, root: Path, tenant_id: str, project_id: str
    ) -> TenantMonitoringExecutionResult:
        del root, tenant_id, project_id
        raise RuntimeError("collector unavailable")

    first = MonitoringWorker(
        root=tmp_path,
        store=store,
        execute=fail_execution,
        clock=lambda: NOW,
    ).run_once(limit=1, retry_delay=timedelta(0))
    second = MonitoringWorker(
        root=tmp_path,
        store=store,
        execute=fail_execution,
        clock=lambda: NOW + timedelta(seconds=1),
    ).run_once(limit=1, retry_delay=timedelta(0))
    final = store.load(tenant_id=TENANT_A, job_id=job.id)

    assert first.retried == 1
    assert second.failed == 1
    assert final.state is MonitoringJobState.failed
    assert final.attempt_count == 2
    assert final.last_error == "collector unavailable"
