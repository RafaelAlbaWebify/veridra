from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra import tenant_monitoring_execution as execution_module
from veridra.core import Assessment
from veridra.email_delivery import EmailAttemptStore
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.tenant_project_store import TenantProjectStore

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
