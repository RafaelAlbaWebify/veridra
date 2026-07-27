# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra import agency_report_web
from veridra.agency_report_web import router
from veridra.core import demo_assessment
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.pdf_reports import PdfDocument
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
MANAGER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.analyst,
    session_id="report-delivery-manager-01",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="report-delivery-viewer-001",
    authenticated_at=NOW,
)


def _client(tmp_path: Path, *, with_assessment: bool = True) -> tuple[TestClient, str]:
    root = tmp_path / "tenants"
    project_id = TenantProjectStore(root).save(
        MANAGER,
        ClientProject.build(name="Client <Report>", target_url="https://example.com"),
    )
    if with_assessment:
        TenantHistoryStore(root).save(MANAGER, project_id, demo_assessment())
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "manager":
            bind_verified_request_identity(request, MANAGER)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), project_id


def test_delivery_confirmation_requires_identity_and_permission(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    anonymous = client.get(f"/agency/projects/{project_id}/reports/send")
    viewer = client.get(
        f"/agency/projects/{project_id}/reports/send",
        headers={"x-test-role": "viewer"},
    )

    assert anonymous.status_code == 401
    assert viewer.status_code == 403


def test_delivery_confirmation_is_read_only_and_escaped(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)
    project_path = tmp_path / "tenants" / MANAGER.tenant_id / "projects" / f"{project_id}.json"
    before = project_path.read_bytes()

    response = client.get(
        f"/agency/projects/{project_id}/reports/send",
        headers={"x-test-role": "manager"},
    )

    assert response.status_code == 200
    assert "Client &lt;Report&gt;" in response.text
    assert "Client <Report>" not in response.text
    assert project_path.read_bytes() == before
    assert not (tmp_path / "tenants" / MANAGER.tenant_id / "report-deliveries").exists()


def test_submit_without_smtp_redirects_to_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, project_id = _client(tmp_path)
    monkeypatch.delenv("VERIDRA_SMTP_HOST", raising=False)
    monkeypatch.delenv("VERIDRA_SMTP_SENDER", raising=False)
    monkeypatch.setattr(
        agency_report_web,
        "render_pdf",
        lambda _html, *, target: PdfDocument(b"%PDF-test", "report.pdf"),
    )

    response = client.post(
        f"/agency/projects/{project_id}/reports/send",
        headers={"x-test-role": "manager"},
        data={
            "recipient": "client@example.com",
            "subject": "Assessment",
            "message": "Attached.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/agency/projects/{project_id}/reports?delivery=not-configured"
    )


def test_invalid_delivery_input_is_rejected(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    response = client.post(
        f"/agency/projects/{project_id}/reports/send",
        headers={"x-test-role": "manager"},
        data={"recipient": "invalid", "subject": "", "message": ""},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Report delivery input is invalid."}


def test_delivery_requires_saved_assessment(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, with_assessment=False)

    response = client.get(
        f"/agency/projects/{project_id}/reports/send",
        headers={"x-test-role": "manager"},
    )

    assert response.status_code == 404
