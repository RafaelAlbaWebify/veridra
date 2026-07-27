# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra import agency_monitoring_web
from veridra.agency_monitoring_web import router
from veridra.core import demo_assessment
from veridra.email_delivery import EmailStatus
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_monitoring_api import MonitoringRunResult
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
ANALYST = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.analyst,
    session_id="analyst-agency-monitoring-01",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="viewer-agency-monitoring-001",
    authenticated_at=NOW,
)


def _client(tmp_path: Path) -> tuple[TestClient, str, str]:
    root = tmp_path / "tenants"
    project = ClientProject.build(
        name="Monitoring <Client>",
        target_url="https://example.com",
    )
    project_id = TenantProjectStore(root).save(ANALYST, project)
    assessment = demo_assessment().model_copy(update={"target": "https://example.com/"})
    assessment_id = TenantHistoryStore(root).save(ANALYST, project_id, assessment)

    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "analyst":
            bind_verified_request_identity(request, ANALYST)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), project_id, assessment_id


def _weekly_form() -> dict[str, str]:
    return {
        "cadence": "weekly",
        "timezone": "Europe/Madrid",
        "hour": "8",
        "minute": "30",
        "weekday": "0",
        "day_of_month": "",
        "recipient": "monitoring@example.com",
    }


def test_monitoring_page_requires_identity(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)

    response = client.get(f"/agency/projects/{project_id}/monitoring")

    assert response.status_code == 401


def test_viewer_can_inspect_but_cannot_change_or_run(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)

    page = client.get(
        f"/agency/projects/{project_id}/monitoring",
        headers={"x-test-role": "viewer"},
    )
    saved = client.post(
        f"/agency/projects/{project_id}/monitoring",
        headers={"x-test-role": "viewer"},
        data=_weekly_form(),
    )
    run = client.post(
        f"/agency/projects/{project_id}/monitoring/run",
        headers={"x-test-role": "viewer"},
    )

    assert page.status_code == 200
    assert "cannot change it" in page.text
    assert "Save monitoring configuration" not in page.text
    assert "Run monitoring now" not in page.text
    assert saved.status_code == 403
    assert run.status_code == 403


def test_get_is_read_only_and_escapes_project_name(tmp_path: Path) -> None:
    client, project_id, assessment_id = _client(tmp_path)
    project_path = tmp_path / "tenants" / ANALYST.tenant_id / "projects" / f"{project_id}.json"
    before = project_path.read_bytes()

    response = client.get(
        f"/agency/projects/{project_id}/monitoring",
        headers={"x-test-role": "analyst"},
    )

    assert response.status_code == 200
    assert "Monitoring &lt;Client&gt;" in response.text
    assert "Monitoring <Client>" not in response.text
    assert project_path.read_bytes() == before
    assert (
        tmp_path
        / "tenants"
        / ANALYST.tenant_id
        / "projects"
        / project_id
        / "assessments"
        / f"{assessment_id}.json"
    ).exists()


def test_analyst_saves_schedule_without_changing_project_or_history(tmp_path: Path) -> None:
    client, project_id, assessment_id = _client(tmp_path)

    response = client.post(
        f"/agency/projects/{project_id}/monitoring",
        headers={"x-test-role": "analyst"},
        data=_weekly_form(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/agency/projects/{project_id}/monitoring?saved=true"
    store = TenantProjectStore(tmp_path / "tenants")
    project = store.load(ANALYST, store.ref(ANALYST, project_id))
    assert project.monitoring_schedule.cadence.value == "weekly"
    assert project.monitoring_schedule.weekday == 0
    assert str(project.monitoring_email) == "monitoring@example.com"
    assert (
        tmp_path
        / "tenants"
        / ANALYST.tenant_id
        / "projects"
        / project_id
        / "assessments"
        / f"{assessment_id}.json"
    ).exists()


def test_invalid_weekly_schedule_is_rejected(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)
    invalid = _weekly_form()
    invalid["weekday"] = ""

    response = client.post(
        f"/agency/projects/{project_id}/monitoring",
        headers={"x-test-role": "analyst"},
        data=invalid,
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Monitoring configuration is invalid."}


def test_manual_run_redirects_with_saved_assessment_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, project_id, _ = _client(tmp_path)
    monkeypatch.setattr(
        agency_monitoring_web,
        "run_monitoring_assessment",
        lambda _project_id, _request, _identity: MonitoringRunResult(
            project_id=project_id,
            assessment_id="f" * 24,
            email_status=EmailStatus.delivered,
        ),
    )

    response = client.post(
        f"/agency/projects/{project_id}/monitoring/run",
        headers={"x-test-role": "analyst"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/agency/projects/{project_id}/monitoring?"
        f"assessment_id={'f' * 24}&email_status=delivered"
    )
