from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra import agency_prospect_discovery_web as web
from veridra.agency_market_study import store_study
from veridra.core import Assessment, demo_assessment
from veridra.crawl import CrawlLimits
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.market_intelligence import add_observations, load, plan
from veridra.prospect_discovery import ObservedBusiness
from veridra.request_security import bind_verified_request_identity

ORIGIN = "http://testserver"
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="market-audit-test",
    authenticated_at=datetime(2026, 10, 10, tzinfo=UTC),
)


def test_market_audit_endpoint_persists_only_approved_manual_evidence(
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
    study = add_observations(
        plan("Galway", "IE", ("dentist",)),
        "dentist",
        [
            ObservedBusiness.model_validate(
                {"provider": "google_maps", "provider_key": "one",
                 "name": "Aster Dental", "country_code": "IE",
                 "website": "https://example.org", "review_count": 50}
            ),
            ObservedBusiness.model_validate(
                {"provider": "google_maps", "provider_key": "two",
                 "name": "Briar Dental", "country_code": "IE"}
            ),
        ],
    )
    store_study(root, OWNER.tenant_id, study)
    url = f"/agency/prospects/discover/market/{study.study_id}/audit"
    identifier = study.businesses[0].business_id
    client = TestClient(app)

    observed: list[str] = []

    def fake_assess(url: str, *, crawl_limits: CrawlLimits) -> Assessment:
        observed.append(url)
        assert crawl_limits.max_pages == 3
        return demo_assessment()

    monkeypatch.setattr(web, "assess_url", fake_assess)
    assert client.post(
        url, data={"business_id": identifier}, headers={"Origin": ORIGIN},
        follow_redirects=False,
    ).status_code == 303
    assert observed == ["https://example.org/"]
    from veridra.agency_market_study import study_path
    restored = load(study_path(root, OWNER.tenant_id, study.study_id))
    assert identifier in restored.website_audits
    assert restored.qualifications == {}
    assert restored.crm_promoted == []
    assert not (root / OWNER.tenant_id / "prospects").exists()

    assert client.post(
        url, data={"business_id": study.businesses[1].business_id},
        headers={"Origin": ORIGIN}, follow_redirects=False,
    ).status_code == 409
    assert client.post(
        url, data={"business_id": "unknown"}, headers={"Origin": ORIGIN},
        follow_redirects=False,
    ).status_code == 404
    assert client.post(
        url, data={"business_id": identifier},
        headers={"Origin": "https://evil.example"}, follow_redirects=False,
    ).status_code in {400, 403}
    assert observed == ["https://example.org/"]
