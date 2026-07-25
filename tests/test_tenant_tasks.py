from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from veridra.identity_tenancy import IdentityBoundaryError, RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.task_store import RemediationTask
from veridra.tenant_project_store import TenantProjectStore
from veridra.tenant_task_api import create_task
from veridra.tenant_task_store import TenantTaskStore

NOW = datetime(2026, 7, 25, 20, 0, tzinfo=UTC)


def _identity(tenant_id: str, role: TenantRole) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _task(project_id: str) -> RemediationTask:
    return RemediationTask(
        project_id=project_id,
        finding_id="missing-security-headers",
        title="Add missing security headers",
        source_assessment_id="c" * 24,
    )


def _request(root: Path) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/tenant/tasks",
            "headers": [],
            "app": app,
        }
    )


def test_same_task_id_is_isolated_between_tenants(tmp_path: Path) -> None:
    store = TenantTaskStore(tmp_path / "tenants")
    first = _identity("1" * 24, TenantRole.analyst)
    second = _identity("2" * 24, TenantRole.analyst)
    task = _task("d" * 24)

    first_id = store.save(first, task)
    second_id = store.save(second, task)

    assert first_id == second_id
    assert store.load(first, store.ref(first, first_id)) == task
    assert store.load(second, store.ref(second, second_id)) == task
    assert (tmp_path / "tenants" / first.tenant_id / "tasks" / f"{first_id}.json").exists()
    assert (tmp_path / "tenants" / second.tenant_id / "tasks" / f"{second_id}.json").exists()


def test_viewer_reads_but_sales_cannot_manage_tasks(tmp_path: Path) -> None:
    store = TenantTaskStore(tmp_path / "tenants")
    tenant_id = "3" * 24
    analyst = _identity(tenant_id, TenantRole.analyst)
    viewer = _identity(tenant_id, TenantRole.viewer)
    sales = _identity(tenant_id, TenantRole.sales)
    task_id = store.save(analyst, _task("e" * 24))

    assert store.list(viewer)[0][0] == task_id
    with pytest.raises(IdentityBoundaryError):
        store.save(sales, _task("e" * 24))


def test_api_refuses_task_for_project_outside_tenant(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    first = _identity("4" * 24, TenantRole.analyst)
    second = _identity("5" * 24, TenantRole.analyst)
    project_id = TenantProjectStore(root).save(
        second,
        ClientProject.build(name="Other project", target_url="https://example.com"),
    )

    with pytest.raises(HTTPException) as captured:
        create_task(_task(project_id), _request(root), first)

    assert captured.value.status_code == 404
    assert not (root / first.tenant_id / "tasks").exists()


def test_api_creates_task_only_after_tenant_project_lookup(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    analyst = _identity("6" * 24, TenantRole.analyst)
    project_id = TenantProjectStore(root).save(
        analyst,
        ClientProject.build(name="Tenant project", target_url="https://example.com"),
    )

    response = create_task(_task(project_id), _request(root), analyst)

    task_id = response["id"]
    assert (root / analyst.tenant_id / "tasks" / f"{task_id}.json").exists()
