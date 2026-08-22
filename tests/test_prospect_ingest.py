from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect, ProspectStatus, StageAQualification
from veridra.prospect_ingest import (
    DiscoveryIngestAction,
    TenantProspectDiscoveryIngestor,
    merge_discovery_prospect,
)
from veridra.tenant_prospect_store import TenantProspectStore

NOW = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.sales,
        session_id="prospect-ingest-session",
        authenticated_at=NOW,
    )


def _prospect(**updates: object) -> Prospect:
    payload: dict[str, object] = {
        "business_name": "Vigo Dental Clinic",
        "website": "https://example.es",
        "sector": "",
        "locality": "Vigo",
        "administrative_area": "",
        "country_code": "ES",
        "phone": "",
        "provider": "manual",
        "provider_key": "",
        "evidence_summary": "Manually identified prospect.",
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(updates)
    return Prospect.model_validate(payload)


def test_ingest_creates_new_discovered_prospect(tmp_path: Path) -> None:
    identity = _identity()
    observed = _prospect(
        provider="fixture",
        provider_key="place-1",
        sector="Dental clinic",
        administrative_area="Pontevedra",
        phone="+34986000000",
        evidence_summary="Observed in local business discovery.",
    )

    outcomes = TenantProspectDiscoveryIngestor(tmp_path).ingest(identity, [observed])

    assert len(outcomes) == 1
    assert outcomes[0].action is DiscoveryIngestAction.created
    saved = TenantProspectStore(tmp_path).load(
        identity,
        TenantProspectStore.ref(identity, outcomes[0].prospect_id),
    )
    assert saved.provider == "fixture"
    assert saved.provider_key == "place-1"
    assert saved.sector == "Dental clinic"


def test_rediscovery_enriches_blanks_without_erasing_human_state(tmp_path: Path) -> None:
    identity = _identity()
    qualification = StageAQualification(
        active_real_business=2,
        website_commercial_importance=2,
        business_economic_value=2,
        business_size_fit=2,
        decision_maker_reachability=1,
        website_manageability=2,
        no_existing_web_team=2,
        reason="Strong commercial fit confirmed by operator.",
    )
    existing = _prospect(
        contact_name="Owner Name",
        contact_email="owner@example.es",
        qualification=qualification,
        status=ProspectStatus.contacted,
        human_verified=True,
        best_observation="Homepage is dated and conversion path is weak.",
        likely_offer="Website refurbishment",
    )
    store = TenantProspectStore(tmp_path)
    prospect_id = store.save(identity, existing)
    observed = _prospect(
        provider="fixture",
        provider_key="place-1",
        sector="Dental clinic",
        administrative_area="Pontevedra",
        phone="+34986000000",
        source_url="https://directory.example/business/1",
        evidence_summary="Observed again with current public business details.",
        updated_at=NOW + timedelta(hours=2),
    )

    outcomes = TenantProspectDiscoveryIngestor(tmp_path).ingest(identity, [observed])
    saved = store.load(identity, store.ref(identity, prospect_id))

    assert outcomes[0].action is DiscoveryIngestAction.enriched
    assert saved.status is ProspectStatus.contacted
    assert saved.qualification == qualification
    assert saved.human_verified is True
    assert saved.contact_name == "Owner Name"
    assert saved.contact_email == "owner@example.es"
    assert saved.best_observation == "Homepage is dated and conversion path is weak."
    assert saved.likely_offer == "Website refurbishment"
    assert saved.provider == "manual"
    assert saved.provider_key == ""
    assert saved.sector == "Dental clinic"
    assert saved.administrative_area == "Pontevedra"
    assert saved.phone == "+34986000000"
    assert str(saved.source_url) == "https://directory.example/business/1"
    assert "Manually identified prospect." in saved.evidence_summary
    assert "Observed again with current public business details." in saved.evidence_summary
    assert saved.updated_at == NOW + timedelta(hours=2)


def test_rediscovery_does_not_replace_nonblank_human_discovery_fields() -> None:
    existing = _prospect(
        sector="Dentist",
        administrative_area="Human checked area",
        phone="+34986111111",
        source_url="https://human.example/source",
    )
    observed = _prospect(
        sector="Medical clinic",
        administrative_area="Machine area",
        phone="+34986222222",
        source_url="https://machine.example/source",
        evidence_summary="Fresh machine evidence.",
        updated_at=NOW + timedelta(hours=1),
    )

    merged = merge_discovery_prospect(existing, observed)

    assert merged.sector == "Dentist"
    assert merged.administrative_area == "Human checked area"
    assert merged.phone == "+34986111111"
    assert str(merged.source_url) == "https://human.example/source"
    assert "Fresh machine evidence." in merged.evidence_summary


def test_identical_rediscovery_is_unchanged(tmp_path: Path) -> None:
    identity = _identity()
    prospect = _prospect(provider="fixture", provider_key="place-1")
    store = TenantProspectStore(tmp_path)
    prospect_id = store.save(identity, prospect)

    outcomes = TenantProspectDiscoveryIngestor(tmp_path).ingest(identity, [prospect])
    saved = store.load(identity, store.ref(identity, prospect_id))

    assert outcomes[0].action is DiscoveryIngestAction.unchanged
    assert saved == prospect
