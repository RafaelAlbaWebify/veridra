"""Isolated HTTP acceptance of Market Study operator decisions through CRM promotion."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra import agency_prospect_discovery_web as web
from veridra.agency_market_study import store_study, study_path
from veridra.core import demo_assessment
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.market_intelligence import add_observations, load, plan
from veridra.prospect_discovery import ObservedBusiness
from veridra.request_security import bind_verified_request_identity

ORIGIN = "http://testserver"
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="market-pipeline-test-session-001",
    authenticated_at=datetime(2026, 10, 11, tzinfo=UTC),
)


def test_market_to_crm_is_explicit_and_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tenants"
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, OWNER)
        return await call_next(request)

    app.include_router(web.router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    study = add_observations(plan("Galway", "IE", ("dentist",)), "dentist", [
        ObservedBusiness.model_validate({
            "provider": "google_maps", "provider_key": "pipeline-1",
            "name": "Aster Dental", "locality": "Galway",
            "country_code": "IE", "website": "https://example.org",
            "observed_at": datetime(2026, 10, 11, tzinfo=UTC),
        }),
    ])
    store_study(root, OWNER.tenant_id, study)
    identifier = study.businesses[0].business_id
    base = f"/agency/prospects/discover/market/{study.study_id}"
    client = TestClient(app)
    headers = {"Origin": ORIGIN}

    def post(action: str, fields: dict[str, str]) -> int:
        return client.post(
            f"{base}/{action}", data=fields, headers=headers,
            follow_redirects=False,
        ).status_code

    # An observation alone must not create a CRM prospect.
    assert post("promote", {"business_id": identifier}) == 409
    assert not (root / OWNER.tenant_id / "prospects").exists()

    assert post("shortlist", {"business_id": identifier, "action": "shortlist"}) == 303
    saved = load(study_path(root, OWNER.tenant_id, study.study_id))
    assert saved.shortlist[identifier] == "shortlist"
    assert saved.crm_promoted == []

    calls: list[str] = []

    def mock_assessment(url: str, *, crawl_limits: object) -> object:
        calls.append(url)
        assert getattr(crawl_limits, "max_pages") == 3
        return demo_assessment()

    monkeypatch.setattr(web, "assess_url", mock_assessment)
    assert post("audit", {"business_id": identifier}) == 303
    assert calls == ["https://example.org/"]
    saved = load(study_path(root, OWNER.tenant_id, study.study_id))
    assert identifier in saved.website_audits
    assert saved.crm_promoted == []
    assert saved.qualifications == {}

    assert post("qualify", {"business_id": identifier, "notes": ""}) == 400
    assert post("qualify", {
        "business_id": identifier,
        "notes": "Human-confirmed potential; operator evidence saved.",
    }) == 303
    saved = load(study_path(root, OWNER.tenant_id, study.study_id))
    assert identifier in saved.qualifications
    assert saved.crm_promoted == []

    assert post("promote", {"business_id": identifier}) == 303
    saved = load(study_path(root, OWNER.tenant_id, study.study_id))
    assert saved.crm_promoted == [identifier]
    assert len(saved.businesses) == 1

    # Idempotency: a second promotion must not create a duplicate.
    assert post("promote", {"business_id": identifier}) == 303
    saved = load(study_path(root, OWNER.tenant_id, study.study_id))
    assert saved.crm_promoted == [identifier]
    assert post("promote", {"business_id": "unknown"}) == 404
    assert post("promote", {"business_id": identifier}) != 409
