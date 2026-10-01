from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from veridra.prospect import ProspectStatus, discovery_signals_from_legacy_evidence
from veridra.prospect_discovery import (
    FixtureDiscoveryProvider,
    ObservedBusiness,
    SearchRequest,
    build_prepared_queries,
    deduplicate_observations,
    normalize_business_name,
    prospects_from_observations,
)

NOW = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)


def _observation(*, provider_key: str = "business-01") -> ObservedBusiness:
    return ObservedBusiness.model_validate(
        {
            "provider": "fixture",
            "provider_key": provider_key,
            "name": "Clínica Álvarez, S.L.",
            "category": "Dental clinic",
            "locality": "Vigo",
            "administrative_area": "Pontevedra",
            "country_code": "ES",
            "website": "https://example.es",
            "phone": "+34986000000",
            "source_url": "https://source.example/business-01",
            "observed_at": NOW,
        }
    )


def test_query_plan_normalizes_country_and_deduplicates_phrases() -> None:
    queries = build_prepared_queries(
        phrases=["dentist", " Dentist ", "", "physiotherapist"],
        territory_name=" Vigo ",
        country_code="es",
    )

    assert [item.sequence for item in queries] == [1, 2]
    assert [item.query_text for item in queries] == [
        "dentist in Vigo, ES",
        "physiotherapist in Vigo, ES",
    ]


def test_query_plan_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="At least one"):
        build_prepared_queries(phrases=["", "  "], territory_name="Vigo", country_code="ES")


def test_business_name_normalization_preserves_leads_behavior() -> None:
    assert normalize_business_name(" Clínica ÁLVAREZ, S.L. ") == "clínica álvarez s l"


def test_provider_identity_deduplication_is_stable() -> None:
    first = _observation(provider_key="Business-01")
    duplicate = first.model_copy(update={"provider_key": "business-01"})
    second = _observation(provider_key="business-02")

    unique = deduplicate_observations([first, duplicate, second])

    assert [item.provider_key for item in unique] == ["Business-01", "business-02"]


def test_observations_become_reviewable_veridra_prospects() -> None:
    prospects = prospects_from_observations([_observation()])

    assert len(prospects) == 1
    prospect = prospects[0]
    assert prospect.business_name == "Clínica Álvarez, S.L."
    assert prospect.status is ProspectStatus.needs_review
    assert prospect.provider_key == "business-01"
    assert prospect.qualification is None
    assert prospect.locality == "Vigo"
    assert "Observed via fixture" in prospect.evidence_summary


def test_fixture_provider_keeps_capture_bounded_and_query_specific(tmp_path: Path) -> None:
    fixture = tmp_path / "businesses.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    **_observation(provider_key="dentist-01").model_dump(mode="json"),
                    "matched_phrases": ["dentist"],
                },
                {
                    **_observation(provider_key="dentist-02").model_dump(mode="json"),
                    "matched_phrases": ["dentist"],
                },
                {
                    **_observation(provider_key="plumber-01").model_dump(mode="json"),
                    "matched_phrases": ["plumber"],
                },
            ]
        ),
        encoding="utf-8",
    )
    provider = FixtureDiscoveryProvider(fixture)

    records = asyncio.run(
        provider.capture_candidates(
            SearchRequest(
                territory_name="Vigo",
                country_code="ES",
                phrase="dentist",
                max_results=1,
            )
        )
    )

    assert len(records) == 1
    assert records[0].provider_key == "dentist-01"


def test_search_request_rejects_unbounded_result_count() -> None:
    with pytest.raises(ValueError, match="between 1 and 200"):
        SearchRequest(
            territory_name="Vigo",
            country_code="ES",
            phrase="dentist",
            max_results=500,
        )


def test_legacy_discovery_evidence_recovers_decimal_rating() -> None:
    signals = discovery_signals_from_legacy_evidence(
        "Observed via google_maps. "
        "Google Maps discovery query: public notary in Dublin, Ireland. "
        "Result rank: 14. Rating: 4.8. Reviews: 221. Photo signal: 3. "
        "Digital-presence opportunity: high (69/100; gap 63, activity 6)."
    )

    assert signals is not None
    assert signals.query_text == "public notary in Dublin, Ireland"
    assert signals.result_rank == 14
    assert signals.rating == 4.8
    assert signals.review_count == 221
    assert signals.photo_signal_count == 3
    assert signals.opportunity_band == "high"
    assert signals.opportunity_score == 69
    assert signals.digital_gap_score == 63
    assert signals.business_activity_score == 6
