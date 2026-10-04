from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient
from httpx import Response

from veridra.agency_prospect_web import router as agency_prospect_router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect, ProspectCommercialLossReason, ProspectStatus
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_prospect_store import TenantProspectStore

ORIGIN = "http://testserver"
NOW = datetime(2026, 8, 22, 18, 30, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="prospect-workbench-session",
        authenticated_at=NOW,
    )


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RequestIdentity]:
    identity = _identity()
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
    monkeypatch.setenv("VERIDRA_ENV", "operator")
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", ORIGIN)
    monkeypatch.setenv(
        "VERIDRA_OUTREACH_PRIVACY_URL",
        "https://webify.example/privacy",
    )
    return TestClient(app), identity


def _create(client: TestClient) -> Response:
    return cast(
        Response,
        client.post(
            "/agency/prospects/new",
            headers={"Origin": ORIGIN},
            data={
                "business_name": "Vigo Dental Clinic",
                "website": "https://example.es",
                "sector": "Dental clinic",
                "locality": "Vigo",
                "administrative_area": "Pontevedra",
                "country_code": "ES",
                "phone": "+34986000000",
                "contact_email": "hello@example.es",
                "evidence_summary": "Active local clinic with an older public website.",
            },
            follow_redirects=False,
        ),
    )


def _prospect_id(created: Response) -> str:
    return created.headers["location"].rsplit("/", 1)[-1]


def _approve_for_outreach(
    store: TenantProspectStore,
    identity: RequestIdentity,
    prospect_id: str,
) -> None:
    prospect = store.load(identity, store.ref(identity, prospect_id))
    store.replace(
        identity,
        store.ref(identity, prospect_id),
        prospect.model_copy(
            update={
                "status": ProspectStatus.approved_for_outreach,
                "outreach_eligible": True,
            }
        ),
    )


def test_operator_can_create_review_and_start_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    created = _create(client)
    assert created.status_code == 303
    detail_url = created.headers["location"]

    index = client.get("/agency/prospects")
    detail = client.get(detail_url)

    assert index.status_code == 200
    assert "Webify prospects" in index.text
    assert "Vigo Dental Clinic" in index.text
    assert "Inbound leads" not in index.text
    assert "Find prospects" in index.text
    assert "website improvement work" in index.text
    assert "refurbishment" not in index.text.lower()
    assert detail.status_code == 200
    assert "<summary>Qualification " in detail.text
    assert "Stage A" not in detail.text
    assert "Commercial progress" in detail.text
    assert "Sales/outreach progression remains locked" in detail.text
    assert "<details class='disclosure' open>" not in detail.text
    assert "Outreach eligibility" in detail.text
    assert "name='outreach_market' maxlength='80' value='Spain'" in detail.text
    assert "Activity history" in detail.text
    assert "/agency/quick-audit" not in detail.text
    assert "Prospect audit" in detail.text


def test_qualification_editor_collapses_after_scoring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))

    response = client.post(
        f"/agency/prospects/{prospect_id}/qualify",
        headers={"Origin": ORIGIN},
        data={
            "active_real_business": "2",
            "website_commercial_importance": "2",
            "business_economic_value": "2",
            "business_size_fit": "2",
            "decision_maker_reachability": "1",
            "website_manageability": "2",
            "no_existing_web_team": "2",
            "reason": "Strong commercial fit.",
            "rejection_reason": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = client.get(f"/agency/prospects/{prospect_id}")
    qualification = detail.text.split("<summary>Qualification ", 1)[1].split(
        "</details>", 1
    )[0]
    assert "<details class='disclosure' open>" not in detail.text.split(
        "<summary>Qualification ", 1
    )[0]
    assert "13/14" in qualification
    assert "Activity history" in detail.text


def test_duplicate_manual_creation_does_not_overwrite_existing_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    first = _create(client)
    prospect_id = _prospect_id(first)
    store = TenantProspectStore(tmp_path)
    original = store.load(identity, store.ref(identity, prospect_id))
    qualified = original.model_copy(
        update={"status": ProspectStatus.contacted, "human_verified": True}
    )
    store.replace(identity, store.ref(identity, prospect_id), qualified)

    duplicate = _create(client)
    saved = store.load(identity, store.ref(identity, prospect_id))

    assert duplicate.status_code == 200
    assert "Prospect already exists" in duplicate.text
    assert saved.status is ProspectStatus.contacted
    assert saved.human_verified is True


def test_strong_stage_a_score_moves_prospect_to_ready_for_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    created = _create(client)
    prospect_id = _prospect_id(created)

    response = client.post(
        f"/agency/prospects/{prospect_id}/qualify",
        headers={"Origin": ORIGIN},
        data={
            "active_real_business": "2",
            "website_commercial_importance": "2",
            "business_economic_value": "2",
            "business_size_fit": "2",
            "decision_maker_reachability": "1",
            "website_manageability": "2",
            "no_existing_web_team": "2",
            "reason": (
                "Active clinic, reachable owner and a commercially important manageable site."
            ),
            "rejection_reason": "",
        },
        follow_redirects=False,
    )

    saved = TenantProspectStore(tmp_path).load(
        identity,
        TenantProspectStore.ref(identity, prospect_id),
    )
    assert response.status_code == 303
    assert saved.status is ProspectStatus.ready_for_audit
    assert saved.qualification is not None
    assert saved.qualification.score == 13
    assert saved.human_verified is True


def test_explicit_rejection_records_reason_and_marks_unsuitable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    created = _create(client)
    prospect_id = _prospect_id(created)

    response = client.post(
        f"/agency/prospects/{prospect_id}/qualify",
        headers={"Origin": ORIGIN},
        data={
            "active_real_business": "2",
            "website_commercial_importance": "1",
            "business_economic_value": "1",
            "business_size_fit": "1",
            "decision_maker_reachability": "0",
            "website_manageability": "1",
            "no_existing_web_team": "0",
            "reason": "The business appears active but there is no realistic direct contact route.",
            "rejection_reason": "NO_CONTACT_ROUTE",
        },
        follow_redirects=False,
    )

    store = TenantProspectStore(tmp_path)
    saved = store.load(identity, store.ref(identity, prospect_id))
    assert response.status_code == 303
    assert saved.status is ProspectStatus.unsuitable
    assert saved.rejection_reason is not None
    assert saved.rejection_reason.value == "NO_CONTACT_ROUTE"


def test_operator_records_contacted_stage_offer_and_message_cohort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))
    store = TenantProspectStore(tmp_path)
    _approve_for_outreach(store, identity, prospect_id)

    response = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={
            "status": "contacted",
            "outreach_offer": "Website Improvement Sprint",
            "message_variant": "dental-vigo-v1",
            "commercial_loss_reason": "",
            "commercial_note": "Personalised email sent to the public clinic address.",
            "first_touch_compliance_confirmed": "yes",
        },
        follow_redirects=False,
    )

    store = TenantProspectStore(tmp_path)
    saved = store.load(identity, store.ref(identity, prospect_id))
    assert response.status_code == 303
    assert saved.status is ProspectStatus.contacted
    assert saved.outreach_offer == "Website Improvement Sprint"
    assert saved.message_variant == "dental-vigo-v1"
    assert saved.commercial_note == "Personalised email sent to the public clinic address."
    assert saved.commercial_loss_reason is None
    assert saved.human_verified is True
    assert saved.privacy_notice_provided_at is not None
    assert saved.first_touch_compliance_confirmed_at is not None


def test_lost_prospect_requires_and_records_commercial_loss_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))

    missing_reason = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={
            "status": "lost",
            "outreach_offer": "Website Improvement Sprint",
            "message_variant": "dental-vigo-v1",
            "commercial_loss_reason": "",
            "commercial_note": "No sale.",
        },
        follow_redirects=False,
    )
    assert missing_reason.status_code == 400

    recorded = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={
            "status": "lost",
            "outreach_offer": "Website Improvement Sprint",
            "message_variant": "dental-vigo-v1",
            "commercial_loss_reason": "EXISTING_PROVIDER",
            "commercial_note": "Owner replied that their current agency handles the website.",
        },
        follow_redirects=False,
    )

    store = TenantProspectStore(tmp_path)
    saved = store.load(identity, store.ref(identity, prospect_id))
    assert recorded.status_code == 303
    assert saved.status is ProspectStatus.lost
    assert saved.commercial_loss_reason is ProspectCommercialLossReason.existing_provider


def test_non_lost_stage_clears_previous_loss_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))
    store = TenantProspectStore(tmp_path)
    original = store.load(identity, store.ref(identity, prospect_id))
    lost = original.model_copy(
        update={
            "status": ProspectStatus.lost,
            "commercial_loss_reason": ProspectCommercialLossReason.no_response,
            "outreach_eligible": True,
        }
    )
    store.replace(identity, store.ref(identity, prospect_id), lost)

    response = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={
            "status": "responded",
            "outreach_offer": "Website Improvement Sprint",
            "message_variant": "dental-vigo-v1",
            "commercial_loss_reason": "NO_RESPONSE",
            "commercial_note": "Late reply arrived and the conversation reopened.",
        },
        follow_redirects=False,
    )

    saved = store.load(identity, store.ref(identity, prospect_id))
    assert response.status_code == 303
    assert saved.status is ProspectStatus.responded
    assert saved.commercial_loss_reason is None


def test_terminal_qualification_rejection_cannot_enter_sales_funnel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))
    store = TenantProspectStore(tmp_path)
    original = store.load(identity, store.ref(identity, prospect_id))
    rejected = original.model_copy(
        update={
            "status": ProspectStatus.unsuitable,
            "rejection_reason": "NO_CONTACT_ROUTE",
        }
    )
    store.replace(identity, store.ref(identity, prospect_id), rejected)

    response = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={"status": "contacted"},
        follow_redirects=False,
    )

    assert response.status_code == 409


def test_prospect_mutations_reject_missing_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    response = client.post(
        "/agency/prospects/new",
        data={"business_name": "No Origin Ltd", "country_code": "ES"},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_customer_stage_cannot_be_set_manually(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))

    detail = client.get(f"/agency/prospects/{prospect_id}")
    assert "value='customer'" not in detail.text

    response = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={"status": "customer"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    saved = TenantProspectStore(tmp_path).load(
        identity,
        TenantProspectStore.ref(identity, prospect_id),
    )
    assert saved.status is ProspectStatus.needs_review


def test_proposal_stage_requires_real_proposal_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))

    detail = client.get(f"/agency/prospects/{prospect_id}")
    assert "value='proposal'" not in detail.text

    response = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={"status": "proposal"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    saved = TenantProspectStore(tmp_path).load(
        identity,
        TenantProspectStore.ref(identity, prospect_id),
    )
    assert saved.status is ProspectStatus.needs_review


def test_prospect_index_filters_and_shows_discovery_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))
    store = TenantProspectStore(tmp_path)
    prospect = store.load(identity, store.ref(identity, prospect_id))
    updated = Prospect.model_validate(
        {
            **prospect.model_dump(mode="json"),
            "business_name": prospect.business_name,
            "sector": "",
            "status": "needs_review",
            "qualification": None,
            "evidence_summary": (
                "Observed via google_maps. "
                "Google Maps discovery query: dentist in Vigo, Spain. "
                "Result rank: 7. Rating: 4.8. Reviews: 42. Photo signal: 5. "
                "Digital-presence opportunity: high "
                "(69/100; gap 45, activity 24)."
            ),
        }
    )
    store.replace(identity, store.ref(identity, prospect_id), updated)

    response = client.get(
        "/agency/prospects"
        "?status=needs_review"
        "&qualification=not-scored"
        "&sort=discovery-desc"
    )

    assert response.status_code == 200
    assert "HIGH 69/100" in response.text
    assert "Maps #7" in response.text
    assert "Dentist" in response.text
    assert "Prepare selected for review" in response.text



def test_initial_contact_requires_explicit_first_touch_compliance_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))
    store = TenantProspectStore(tmp_path)
    _approve_for_outreach(store, identity, prospect_id)

    response = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={
            "status": "contacted",
            "outreach_offer": "Website Improvement Sprint",
            "message_variant": "dental-vigo-v1",
            "commercial_loss_reason": "",
            "commercial_note": "Attempted first contact.",
        },
        follow_redirects=False,
    )

    saved = store.load(identity, store.ref(identity, prospect_id))
    assert response.status_code == 400
    assert saved.status is ProspectStatus.approved_for_outreach
    assert saved.privacy_notice_provided_at is None
    assert saved.first_touch_compliance_confirmed_at is None


def test_objection_creates_tenant_suppression_and_blocks_same_email_elsewhere(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    first_id = _prospect_id(_create(client))
    store = TenantProspectStore(tmp_path)
    first = store.load(identity, store.ref(identity, first_id))
    store.replace(
        identity,
        store.ref(identity, first_id),
        first.model_copy(
            update={
                "status": ProspectStatus.audited,
                "audit_assessment_id": "c" * 24,
                "webify_fixable": True,
            }
        ),
    )

    first_review = client.post(
        f"/agency/prospects/{first_id}/outreach-review",
        headers={"Origin": ORIGIN},
        data={
            "outreach_market": "Ireland",
            "outreach_mailbox_type": "corporate",
            "contact_source": "Business website",
            "contact_source_url": "https://example.es/contact",
            "named_contact_role": "",
            "role_relevance_basis": "",
            "privacy_notice_ready": "yes",
            "suppression_checked": "yes",
            "objection_received": "yes",
            "outreach_ineligible_reason": "",
        },
        follow_redirects=False,
    )
    assert first_review.status_code == 303

    second = Prospect(
        business_name="Another Dental Clinic",
        website="https://another.example",
        sector="Dental clinic",
        locality="Dublin",
        country_code="IE",
        contact_email="hello@example.es",
        status=ProspectStatus.audited,
        audit_assessment_id="d" * 24,
        webify_fixable=True,
    )
    second_id = store.save(identity, second)

    second_review = client.post(
        f"/agency/prospects/{second_id}/outreach-review",
        headers={"Origin": ORIGIN},
        data={
            "outreach_market": "Ireland",
            "outreach_mailbox_type": "corporate",
            "contact_source": "Business website",
            "contact_source_url": "https://another.example/contact",
            "named_contact_role": "",
            "role_relevance_basis": "",
            "privacy_notice_ready": "yes",
            "suppression_checked": "yes",
            "outreach_ineligible_reason": "",
        },
        follow_redirects=False,
    )

    saved = store.load(identity, store.ref(identity, second_id))
    assert second_review.status_code == 303
    assert saved.status is ProspectStatus.audited
    assert saved.outreach_eligible is False
    assert "suppression register" in saved.outreach_ineligible_reason
    assert saved.privacy_notice_url == "https://webify.example/privacy"


def test_suppressed_contact_cannot_be_marked_contacted_even_if_record_was_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    prospect_id = _prospect_id(_create(client))
    store = TenantProspectStore(tmp_path)
    _approve_for_outreach(store, identity, prospect_id)

    from veridra.outreach_suppression import TenantOutreachSuppressionStore

    TenantOutreachSuppressionStore(tmp_path).suppress(
        identity,
        email="hello@example.es",
        reason="Prior objection",
        source_prospect_id=prospect_id,
    )

    response = client.post(
        f"/agency/prospects/{prospect_id}/commercial",
        headers={"Origin": ORIGIN},
        data={
            "status": "contacted",
            "first_touch_compliance_confirmed": "yes",
        },
        follow_redirects=False,
    )

    saved = store.load(identity, store.ref(identity, prospect_id))
    assert response.status_code == 400
    assert saved.status is ProspectStatus.approved_for_outreach



def test_outreach_review_fails_closed_without_public_privacy_notice_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, identity = _client(tmp_path, monkeypatch)
    monkeypatch.delenv("VERIDRA_OUTREACH_PRIVACY_URL", raising=False)
    prospect_id = _prospect_id(_create(client))
    store = TenantProspectStore(tmp_path)
    prospect = store.load(identity, store.ref(identity, prospect_id))
    store.replace(
        identity,
        store.ref(identity, prospect_id),
        prospect.model_copy(
            update={
                "status": ProspectStatus.audited,
                "audit_assessment_id": "e" * 24,
                "webify_fixable": True,
            }
        ),
    )

    response = client.post(
        f"/agency/prospects/{prospect_id}/outreach-review",
        headers={"Origin": ORIGIN},
        data={
            "outreach_market": "Ireland",
            "outreach_mailbox_type": "corporate",
            "contact_source": "Business website",
            "privacy_notice_ready": "yes",
            "suppression_checked": "yes",
            "outreach_ineligible_reason": "",
        },
        follow_redirects=False,
    )

    saved = store.load(identity, store.ref(identity, prospect_id))
    assert response.status_code == 303
    assert saved.status is ProspectStatus.audited
    assert saved.outreach_eligible is False
    assert "public HTTPS Webify Privacy Notice URL" in saved.outreach_ineligible_reason
    assert saved.privacy_notice_url == ""
