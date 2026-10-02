from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra import tenant_monitoring_execution as execution_module
from veridra.core import Assessment, Finding, Status
from veridra.email_delivery import EmailAttemptStore
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import (
    PlanName,
    UsageKind,
    WorkspaceConfig,
    WorkspacePolicyError,
    WorkspaceStore,
    usage_period,
)

NOW = datetime(2026, 7, 26, 20, 0, tzinfo=UTC)
TENANT_ID = "a" * 24


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="b" * 24,
        tenant_id=TENANT_ID,
        membership_role=TenantRole.owner,
        session_id="worker-proof-session-value",
        authenticated_at=NOW,
    )


def test_execution_writes_only_tenant_qualified_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _identity()
    project_id = TenantProjectStore(tmp_path).save(
        identity,
        ClientProject.build(name="Worker project", target_url="https://example.com"),
    )
    assessment = Assessment.build(
        "https://example.com",
        [],
        generated_at=NOW,
    )
    selected_email_directory: list[Path] = []

    def fake_assess_url(raw_url: str, **kwargs: object) -> Assessment:
        del kwargs
        assert raw_url == "https://example.com"
        return assessment

    def fake_send_monitoring_summary(**kwargs: object) -> None:
        store = kwargs["store"]
        assert isinstance(store, EmailAttemptStore)
        selected_email_directory.append(store.directory)
        return None

    monkeypatch.setattr(execution_module, "assess_url", fake_assess_url)
    monkeypatch.setattr(
        execution_module,
        "send_monitoring_summary",
        fake_send_monitoring_summary,
    )

    result = execution_module.execute_tenant_monitoring(
        root=tmp_path,
        tenant_id=TENANT_ID,
        project_id=project_id,
    )

    assessment_path = (
        tmp_path
        / TENANT_ID
        / "projects"
        / project_id
        / "assessments"
        / f"{result.assessment_id}.json"
    )
    assert assessment_path.exists()
    assert selected_email_directory == [tmp_path / TENANT_ID / "email-deliveries"]
    assert not (tmp_path / "history").exists()
    assert not (tmp_path / "email-deliveries").exists()


def test_hosted_monitoring_blocks_when_monitoring_allowance_is_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _identity()
    project_id = TenantProjectStore(tmp_path).save(
        identity,
        ClientProject.build(name="Free project", target_url="https://example.com"),
    )
    WorkspaceStore(tmp_path / TENANT_ID / "workspace").save(
        WorkspaceConfig(plan=PlanName.free)
    )
    called = False

    def fake_assess_url(raw_url: str, **kwargs: object) -> Assessment:
        nonlocal called
        called = True
        del raw_url, kwargs
        return Assessment.build("https://example.com", [], generated_at=NOW)

    monkeypatch.setattr(execution_module, "assess_url", fake_assess_url)

    with pytest.raises(WorkspacePolicyError, match="monitoring_run"):
        execution_module.execute_tenant_monitoring(
            root=tmp_path,
            tenant_id=TENANT_ID,
            project_id=project_id,
            enforce_entitlements=True,
        )

    assert called is False


def test_hosted_monitoring_records_run_and_actual_crawled_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _identity()
    project_id = TenantProjectStore(tmp_path).save(
        identity,
        ClientProject.build(name="Agency project", target_url="https://example.com"),
    )
    WorkspaceStore(tmp_path / TENANT_ID / "workspace").save(
        WorkspaceConfig(plan=PlanName.agency)
    )
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="crawl.http-status",
                area="Website health",
                title="Multi-page page response",
                status=Status.passed,
                severity="info",
                summary="Crawl completed.",
                evidence={"crawled_pages": 4},
            )
        ],
        generated_at=NOW,
    )

    monkeypatch.setattr(
        execution_module,
        "assess_url",
        lambda _url, **_kwargs: assessment,
    )
    monkeypatch.setattr(
        execution_module,
        "send_monitoring_summary",
        lambda **_kwargs: None,
    )

    result = execution_module.execute_tenant_monitoring(
        root=tmp_path,
        tenant_id=TENANT_ID,
        project_id=project_id,
        enforce_entitlements=True,
    )

    policy = TenantWorkspacePolicy(tmp_path)
    totals = policy.usage_ledger(identity).totals(
        usage_period(policy.load(identity))
    )
    assert result.assessment_id
    assert totals[UsageKind.monitoring_run] == 1
    assert totals[UsageKind.crawled_page] == 4
    assert list(
        (tmp_path / TENANT_ID / "workspace" / "usage-reservations").glob("*.json")
    ) == []
