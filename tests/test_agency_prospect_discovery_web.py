from __future__ import annotations

from datetime import UTC, datetime

from veridra.agency_prospect_discovery_web import (
    _clean_sector,
    _prospect_for_ingest,
    _review_table,
)
from veridra.assisted_discovery import TraversalObservation
from veridra.prospect_discovery import ObservedBusiness


def _observation(
    *,
    rank: int = 1,
    name: str = "Example Dental",
    category: str = "Dentist",
    website: str | None = "https://example.test/",
) -> TraversalObservation:
    return TraversalObservation(
        business=ObservedBusiness.model_validate(
            {
                "provider": "google_maps",
                "provider_key": f"google-maps:{rank}",
                "name": name,
                "category": category,
                "locality": "Vigo",
                "administrative_area": "Pontevedra",
                "country_code": "ES",
                "website": website,
                "source_url": f"https://www.google.com/maps/place/example-{rank}",
                "observed_at": datetime(2026, 8, 23, 15, 0, tzinfo=UTC),
            }
        ),
        query_text="dentist in Vigo, ES",
        query_sequence=1,
        result_rank=rank,
        first_seen_scroll_step=0,
    )


def test_clean_sector_rejects_name_echo_and_sponsored_label() -> None:
    assert _clean_sector(_observation(name="Clinic One", category="Clinic One")) == ""
    assert _clean_sector(_observation(category="Sponsored")) == ""
    assert _clean_sector(_observation(category="Dentist")) == "Dentist"


def test_prospect_for_ingest_preserves_provenance_and_review_state() -> None:
    prospect = _prospect_for_ingest(_observation(rank=3))

    assert prospect.business_name == "Example Dental"
    assert str(prospect.website) == "https://example.test/"
    assert prospect.sector == "Dentist"
    assert prospect.provider == "google_maps"
    assert prospect.provider_key == "google-maps:3"
    assert prospect.status.value == "needs_review"
    assert "dentist in Vigo, ES" in prospect.evidence_summary
    assert "Result rank: 3" in prospect.evidence_summary


def test_review_table_disables_no_website_rows_and_requires_explicit_selection() -> None:
    html = _review_table(
        (
            _observation(rank=1, website="https://example.test/"),
            _observation(rank=2, name="Sponsored Clinic", category="Sponsored", website=None),
        )
    )

    assert "name='selected_rank' value='1'" in html
    assert "name='selected_rank' value='2'" not in html
    assert "No website" in html
    assert "checked" not in html
