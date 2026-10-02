from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import veridra.crawl_worker as worker_module
import veridra.tenant_crawl_execution as execution_module
from veridra.core import Assessment, Finding, Status
from veridra.crawl_jobs import CrawlJobState, SQLiteCrawlJobStore
from veridra.crawl_worker import CrawlWorker
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.tenant_crawl_execution import TenantCrawlExecutionResult
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import (
    PlanName,
    UsageKind,
    WorkspaceConfig,
    usage_period,
)

NOW = datetime(2026, 10, 2, 12, 30, tzinfo=UTC)
TENANT = "a" * 24
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id=TENANT,
    membership_role=TenantRole.owner,
    session_id="crawl-worker-owner-session",
    authenticated_at=NOW,
)


def _fixture(
    tmp_path: Path,
    *,
    max_attempts: int = 3,
) -> tuple[Path, str, SQLiteCrawlJobStore, str]:
    root = tmp_path / "tenants"
    policy = TenantWorkspacePolicy(root)
    policy.save(OWNER, WorkspaceConfig(plan=PlanName.agency))
    project_id = TenantProjectStore(root).save(
        OWNER,
        ClientProject.build(
            name="Worker project",
            target_url="https://example.com/",
            crawl_profile="quick",
        ),
    )
    workspace = policy.load(OWNER)
    ledger = policy.usage_ledger(OWNER)
    audit_reservation = ledger.reserve(
        workspace,
        UsageKind.audit,
        now=NOW,
        lifetime=timedelta(hours=24),
    )
    page_reservation = ledger.reserve(
        workspace,
        UsageKind.crawled_page,
        quantity=10,
        now=NOW,
        lifetime=timedelta(hours=24),
    )
    store = SQLiteCrawlJobStore(root / "crawl-jobs.sqlite3")
    job = store.enqueue(
        tenant_id=TENANT,
        project_id=project_id,
        target_url="https://example.com/",
        crawl_profile="quick",
        page_budget=10,
        request_key="worker-test",
        now=NOW,
        max_attempts=max_attempts,
        max_active_for_tenant=4,
        audit_reservation_id=audit_reservation,
        page_reservation_id=page_reservation,
    )
    return root, project_id, store, job.id


def _assessment(*, pages: int = 4) -> Assessment:
    return Assessment.build(
        "https://example.com/",
        [
            Finding(
                id="crawl.http-status",
                area="Website health",
                title="Multi-page response",
                status=Status.passed,
                severity="info",
                summary="Crawl completed.",
                evidence={"crawled_pages": pages},
            )
        ],
        generated_at=NOW,
    )


def test_worker_executes_project_crawl_saves_history_and_consumes_actual_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, project_id, store, job_id = _fixture(tmp_path)
    assess_calls: list[str] = []

    def fake_assess(raw_url: str, **kwargs: object) -> Assessment:
        assess_calls.append(raw_url)
        progress = kwargs["crawl_progress"]
        assert callable(progress)
        progress(1)
        progress(4)
        return _assessment(pages=4)

    monkeypatch.setattr(execution_module, "assess_url", fake_assess)

    result = CrawlWorker(
        root=root,
        store=store,
        execute=execution_module.execute_tenant_crawl_job,
        clock=lambda: NOW,
    ).run_once(limit=1)

    final = store.load(tenant_id=TENANT, job_id=job_id)
    history = TenantHistoryStore(root).list(OWNER, project_id)
    policy = TenantWorkspacePolicy(root)
    totals = policy.usage_ledger(OWNER).totals(
        usage_period(policy.load(OWNER), now=NOW)
    )

    assert result.leased == 1
    assert result.succeeded == 1
    assert result.retried == 0
    assert result.failed == 0
    assert assess_calls == ["https://example.com/"]
    assert final.state is CrawlJobState.succeeded
    assert final.pages_completed == 4
    assert final.assessment_id is not None
    assert len(history) == 1
    assert totals[UsageKind.audit] == 1
    assert totals[UsageKind.crawled_page] == 4
    assert list(
        (root / TENANT / "workspace" / "usage-reservations").glob("*.json")
    ) == []


def test_metering_retry_reuses_persisted_assessment_without_recrawling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, project_id, store, job_id = _fixture(tmp_path, max_attempts=3)
    assess_count = 0

    def fake_assess(_raw_url: str, **_kwargs: object) -> Assessment:
        nonlocal assess_count
        assess_count += 1
        return _assessment(pages=3)

    monkeypatch.setattr(execution_module, "assess_url", fake_assess)
    original_reconcile = worker_module._reconcile_usage
    reconcile_calls = 0

    def fail_once(**kwargs: object) -> None:
        nonlocal reconcile_calls
        reconcile_calls += 1
        if reconcile_calls == 1:
            raise RuntimeError("simulated metering interruption")
        original_reconcile(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(worker_module, "_reconcile_usage", fail_once)

    worker = CrawlWorker(
        root=root,
        store=store,
        execute=execution_module.execute_tenant_crawl_job,
        clock=lambda: NOW,
    )
    first = worker.run_once(limit=1, retry_delay=timedelta(0))
    second = worker.run_once(limit=1, retry_delay=timedelta(0))

    final = store.load(tenant_id=TENANT, job_id=job_id)
    history = TenantHistoryStore(root).list(OWNER, project_id)
    policy = TenantWorkspacePolicy(root)
    totals = policy.usage_ledger(OWNER).totals(
        usage_period(policy.load(OWNER), now=NOW)
    )

    assert first.retried == 1
    assert second.succeeded == 1
    assert assess_count == 1
    assert reconcile_calls == 2
    assert final.state is CrawlJobState.succeeded
    assert final.assessment_id is not None
    assert len(history) == 1
    assert totals[UsageKind.audit] == 1
    assert totals[UsageKind.crawled_page] == 3


def test_terminal_worker_failure_releases_unconsumed_reservations(
    tmp_path: Path,
) -> None:
    root, _, store, job_id = _fixture(tmp_path, max_attempts=1)

    def fail_execution(**_kwargs: object) -> TenantCrawlExecutionResult:
        raise RuntimeError("collector unavailable")

    result = CrawlWorker(
        root=root,
        store=store,
        execute=fail_execution,
        clock=lambda: NOW,
    ).run_once(limit=1, retry_delay=timedelta(0))

    final = store.load(tenant_id=TENANT, job_id=job_id)
    policy = TenantWorkspacePolicy(root)
    effective = policy.usage_ledger(OWNER).effective_totals(
        usage_period(policy.load(OWNER), now=NOW),
        now=NOW,
    )

    assert result.failed == 1
    assert final.state is CrawlJobState.failed
    assert effective.get(UsageKind.audit, 0) == 0
    assert effective.get(UsageKind.crawled_page, 0) == 0
    assert list(
        (root / TENANT / "workspace" / "usage-reservations").glob("*.json")
    ) == []


def test_worker_rejects_project_configuration_drift_without_cross_tenant_output(
    tmp_path: Path,
) -> None:
    root, project_id, store, job_id = _fixture(tmp_path, max_attempts=1)
    projects = TenantProjectStore(root)
    projects.replace(
        OWNER,
        projects.ref(OWNER, project_id),
        ClientProject.build(
            name="Changed worker project",
            target_url="https://changed.example/",
            crawl_profile="quick",
        ),
    )

    result = CrawlWorker(
        root=root,
        store=store,
        execute=execution_module.execute_tenant_crawl_job,
        clock=lambda: NOW,
    ).run_once(limit=1)

    final = store.load(tenant_id=TENANT, job_id=job_id)

    assert result.failed == 1
    assert final.state is CrawlJobState.failed
    assert "target no longer matches" in (final.last_error or "")
    assert not (root / TENANT / "projects" / project_id / "assessments").exists()
