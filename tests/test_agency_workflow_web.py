from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_workflow_web import router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import bind_verified_request_identity

OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="operator-home-test-session",
    authenticated_at=datetime(2026, 9, 30, tzinfo=UTC),
)


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    environment: str = "operator",
) -> TestClient:
    monkeypatch.setenv("VERIDRA_ENV", environment)
    app = FastAPI()

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, OWNER)
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def test_operator_home_explains_current_webify_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).get("/agency")

    assert response.status_code == 200
    assert "VERIDRA operator" in response.text
    assert "1. Discover" in response.text
    assert "2. Qualify" in response.text
    assert "3. Audit" in response.text
    assert "4. Win work" in response.text
    assert "5. Prove" in response.text
    assert "Prospect discovery" in response.text
    assert "Quick audit" in response.text
    assert "Sales / proposals" in response.text
    assert "Customers" in response.text
    assert "Client projects" in response.text
    assert "Presence Care" in response.text
    assert "href='/agency/prospects/discover'" in response.text


def test_operator_home_does_not_expose_saas_or_inbound_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).get("/agency")

    assert response.status_code == 200
    for forbidden in (
        "href='/agency/leads'",
        "href='/agency/lead-forms'",
        "href='/workspace'",
        "href='/workspace/members'",
        "Plan and usage",
        "Team",
        "Inbound leads",
        "Lead forms",
    ):
        assert forbidden not in response.text


def test_quick_audit_handoff_redirects_to_temporary_agency_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).get(
        "/agency/quick-audit",
        params={"target": "  https://example.com/path?a=1&b=2  "},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/agency/audit?url=https%3A%2F%2Fexample.com%2Fpath%3Fa%3D1%26b%3D2"
    )


def test_hosted_home_uses_agency_product_copy_and_exposes_hosted_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch, environment="production").get("/agency")

    assert response.status_code == 200
    assert "VERIDRA agency workspace" in response.text
    assert "Agency workspace" in response.text
    assert "Webify operator" not in response.text
    assert "Operator rule:" not in response.text
    assert "href='/agency/leads'" in response.text
    assert "href='/agency/lead-forms'" in response.text
    assert "href='/workspace'" in response.text
    assert "href='/workspace/members'" in response.text
    assert "Inbound leads" in response.text
    assert "Lead forms" in response.text
