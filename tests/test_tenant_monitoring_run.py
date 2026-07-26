from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from veridra.core import Assessment, Finding, Status
from veridra.email_delivery import EmailAttemptStore
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.tenant_monitoring_api import run_monitoring_assessment
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 26, 1, 0, tzinfo=UTC)


def _identity(tenant_id: str) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=TenantRole.analyst,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _request(root: Path) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/tenant/monitoring/test/run",
            "headers": [],
            "app": app,
        }
    )


def _assessment() -> Assessment:
    return Assessment.build(
        "https://example.com",
        [
            Finding(
                id="health.title",
                area="Website health",
                title="Title present",
                status=Status.passed,
                severity="info",
                summary="Title is present.",
            )
        ],
        generated_at=NOW,
    )


def test_monitoring_run_writes_only_tenant_history_and_delivery_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tenants"
    identity = _identity("1" * 24)
    project_id = TenantProjectStore(root).save(
        identity,
        ClientProject.build(
            name="Monitored project",
            target_url="https://example.com",
            monitoring_email="monitoring@example.com",
        ),
    )
    assessment = _assessment()
    selected: dict[str, object] = {}

    def fake_assess_url(*args: object, **kwargs: object) -> Assessment:
        return assessment

    def fake_send_monitoring_summary(**kwargs: object) -> None:
        selected.update(kwargs)

    monkeypatch.setattr(
        "veridra.tenant_monitoring_api.assess_url",
        fake_assess_url,
    )
    monkeypatch.setattr(
        "veridra.tenant_monitoring_api.send_monitoring_summary",
        fake_send_monitoring_summary,
    )

    result = run_monitoring_assessment(
        project_id,
        _request(root),
        identity,
    )

    history_path = (
        root
        / identity.tenant_id
        / "projects"
        / project_id
        / "assessments"
        / f"{result.assessment_id}.json"
    )
    assert history_path.exists()
    assert result.email_status is None
    assert selected["assessment_id"] == result.assessment_id
    assert selected["recipient"] == "monitoring@example.com"
    attempt_store = selected["store"]
    assert isinstance(attempt_store, EmailAttemptStore)
    assert attempt_store.directory == root / identity.tenant_id / "email-deliveries"
    assert not (tmp_path / "history").exists()
    assert not (tmp_path / "email-deliveries").exists()
