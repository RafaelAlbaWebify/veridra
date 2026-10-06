from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_commercial_dashboard_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import bind_verified_request_identity

OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="operator-commercial-dashboard",
    authenticated_at=datetime(2026, 10, 6, 14, 0, tzinfo=UTC),
)


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path / "tenants"

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, OWNER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def test_operator_commercial_dashboard_uses_webify_sales_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", "operator")
    response = _client(tmp_path).get("/agency/commercial")

    assert response.status_code == 200
    assert "<h1>Sales dashboard</h1>" in response.text
    assert "Webify operator view" in response.text
    assert "href='/agency/deals'>Sales / proposals</a>" in response.text
    assert "Prospect → customer conversion" in response.text
    assert "Due prospect follow-ups" in response.text
    assert "Inbound leads" not in response.text
    assert "Inbound win rate" not in response.text
    assert "Tenant-scoped" not in response.text
    assert "saved tenant projects" not in response.text
    assert "href='/agency/leads'" not in response.text


def test_non_operator_dashboard_retains_inbound_lead_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_ENV", "production")
    response = _client(tmp_path).get("/agency/commercial")

    assert response.status_code == 200
    assert "<h1>Commercial dashboard</h1>" in response.text
    assert "Tenant-scoped view" in response.text
    assert "Inbound leads" in response.text
    assert "Inbound win rate" in response.text
    assert "href='/agency/leads'" in response.text
