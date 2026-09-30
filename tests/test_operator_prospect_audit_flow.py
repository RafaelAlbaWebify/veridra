from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra import agency_prospect_web
from veridra.agency_prospect_web import router
from veridra.core import demo_assessment
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect, ProspectStatus, StageAQualification
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_prospect_audit_store import TenantProspectAuditStore
from veridra.tenant_prospect_store import TenantProspectStore

NOW = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)
ORIGIN = "http://testserver"
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="operator-prospect-audit-flow",
    authenticated_at=NOW,
)


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path, str]:
    root = tmp_path / "tenants"
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(request, OWNER)
        return await call_next(request)

    app.include_router(router)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    monkeypatch.setattr(agency_prospect_web, "assess_url", lambda _url: demo_assessment())

    prospect = Prospect(
        business_name="Operator Audit Dental",
        website="https://example.com",
        sector="Dental clinic",
        locality="Dublin",
        administrative_area="Dublin",
        country_code="IE",
        contact_email="reception@example.com",
        qualification=StageAQualification(
            active_real_business=2,
            website_commercial_importance=2,
            business_economic_value=2,
            business_size_fit=2,
            decision_maker_reachability=2,
            website_manageability=2,
            no_existing_web_team=2,
            reason="Synthetic audit-ready prospect.",
        ),
        status=ProspectStatus.ready_for_audit,
    )
    prospect_id = TenantProspectStore(root).save(OWNER, prospect)
    return TestClient(app), root, prospect_id


def _post(client: TestClient, path: str, data: dict[str, str] | None = None):
    return client.post(
        path,
        headers={"Origin": ORIGIN},
        data=data or {},
        follow_redirects=False,
    )


def test_prospect_audit_persists_without_creating_client_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, root, prospect_id = _client(tmp_path, monkeypatch)

    response = _post(client, f"/agency/prospects/{prospect_id}/audit")
    assert response.status_code == 303

    prospect_store = TenantProspectStore(root)
    prospect = prospect_store.load(OWNER, prospect_store.ref(OWNER, prospect_id))
    assert prospect.status is ProspectStatus.audited
    assert prospect.audit_assessment_id
    assert prospect.audited_at is not None
    assert prospect.best_observation

    audit_store = TenantProspectAuditStore(root)
    entries = audit_store.list(OWNER, prospect_id)
    assert [item.id for item in entries] == [prospect.audit_assessment_id]

    project_root = root / OWNER.tenant_id / "projects"
    assert not project_root.exists() or not list(project_root.glob("*.json"))


def test_outreach_requires_audit_review_and_compliance_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, root, prospect_id = _client(tmp_path, monkeypatch)
    assert _post(client, f"/agency/prospects/{prospect_id}/audit").status_code == 303

    blocked = _post(
        client,
        f"/agency/prospects/{prospect_id}/commercial",
        {"status": "contacted"},
    )
    assert blocked.status_code == 400

    reviewed = _post(
        client,
        f"/agency/prospects/{prospect_id}/audit/review",
        {
            "best_observation": "The public site has a fixable trust-signal gap.",
            "webify_fixable": "yes",
            "estimated_effort_hours": "1.5",
            "likely_offer": "Digital Presence Assessment & Improvement",
        },
    )
    assert reviewed.status_code == 303

    eligibility = _post(
        client,
        f"/agency/prospects/{prospect_id}/outreach-review",
        {
            "outreach_market": "Ireland",
            "outreach_mailbox_type": "corporate",
            "contact_source": "Business website",
            "contact_source_url": "https://example.com/contact",
            "privacy_notice_ready": "yes",
            "suppression_checked": "yes",
        },
    )
    assert eligibility.status_code == 303

    prospect_store = TenantProspectStore(root)
    approved = prospect_store.load(OWNER, prospect_store.ref(OWNER, prospect_id))
    assert approved.status is ProspectStatus.approved_for_outreach
    assert approved.outreach_eligible is True
    assert approved.suppression_checked_at is not None

    contacted = _post(
        client,
        f"/agency/prospects/{prospect_id}/commercial",
        {
            "status": "contacted",
            "outreach_offer": "Digital Presence Assessment & Improvement",
            "message_variant": "ireland-dental-v1",
            "commercial_note": "Synthetic explicit operator send recorded.",
        },
    )
    assert contacted.status_code == 303

    final = prospect_store.load(OWNER, prospect_store.ref(OWNER, prospect_id))
    assert final.status is ProspectStatus.contacted
