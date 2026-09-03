from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient

from veridra.agency_prospect_web import router as agency_prospect_router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import bind_verified_request_identity

NOW = datetime(2026, 9, 3, 5, 30, tzinfo=UTC)


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    identity = RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="prospect-country-default-session",
        authenticated_at=NOW,
    )
    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path

    @app.middleware("http")
    async def bind_identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[FastAPIResponse]],
    ) -> FastAPIResponse:
        bind_verified_request_identity(request, identity)
        return await call_next(request)

    app.include_router(agency_prospect_router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://testserver")
    return TestClient(app)


def test_new_manual_prospect_form_has_no_spain_specific_country_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(tmp_path, monkeypatch).get("/agency/prospects/new")

    assert response.status_code == 200
    assert "name='country_code' maxlength='2' value='ES'" not in response.text
    assert "name='country_code' maxlength='2' placeholder='US, IE, GB, etc.'" in response.text
