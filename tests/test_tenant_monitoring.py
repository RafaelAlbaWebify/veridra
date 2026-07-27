from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.monitoring_schedule import MonitoringCadence, MonitoringSchedule
from veridra.project_store import ClientProject
from veridra.tenant_monitoring_api import (
    MonitoringConfigurationUpdate,
    get_monitoring_configuration,
    replace_monitoring_configuration,
)
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 25, 21, 0, tzinfo=UTC)


def _identity(tenant_id: str, role: TenantRole) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _request(root: Path) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    return Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/api/tenant/monitoring/test",
            "headers": [],
            "app": app,
        }
    )


def test_monitoring_update_preserves_tenant_project_identity(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    analyst = _identity("1" * 24, TenantRole.analyst)
    store = TenantProjectStore(root)
    project_id = store.save(
        analyst,
        ClientProject.build(name="Tenant project", target_url="https://example.com"),
    )
    payload = MonitoringConfigurationUpdate(
        schedule=MonitoringSchedule(
            cadence=MonitoringCadence.weekly,
            timezone="Europe/Madrid",
            hour=8,
            minute=30,
            weekday=0,
        ),
        recipient="monitoring@example.com",
    )

    response = replace_monitoring_configuration(
        project_id,
        payload,
        _request(root),
        analyst,
    )

    assert response.project_id == project_id
    assert response.schedule == payload.schedule
    assert str(response.recipient) == "monitoring@example.com"
    replacement = store.load(analyst, store.ref(analyst, project_id))
    assert replacement.monitoring_schedule == payload.schedule
    assert str(replacement.monitoring_email) == "monitoring@example.com"


def test_viewer_reads_monitoring_configuration(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    tenant_id = "2" * 24
    analyst = _identity(tenant_id, TenantRole.analyst)
    viewer = _identity(tenant_id, TenantRole.viewer)
    project_id = TenantProjectStore(root).save(
        analyst,
        ClientProject.build(name="Readable project", target_url="https://example.com"),
    )

    response = get_monitoring_configuration(project_id, _request(root), viewer)

    assert response.project_id == project_id
    assert response.schedule.cadence == MonitoringCadence.manual
    assert response.recipient is None


def test_cross_tenant_monitoring_project_is_concealed(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    first = _identity("3" * 24, TenantRole.analyst)
    second = _identity("4" * 24, TenantRole.analyst)
    project_id = TenantProjectStore(root).save(
        second,
        ClientProject.build(name="Other project", target_url="https://example.com"),
    )

    with pytest.raises(HTTPException) as captured:
        get_monitoring_configuration(project_id, _request(root), first)

    assert captured.value.status_code == 404
