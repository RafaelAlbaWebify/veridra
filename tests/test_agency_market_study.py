# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path

from veridra.agency_market_study import (
    _coordinates_from_maps_url,
    all_studies,
    geographic_overview,
    input_json,
    market_detail,
    market_overview,
    next_pending_sector,
    sector_chart,
    store_study,
    study_path,
)
from veridra.market_intelligence import plan


def test_market_studies_are_tenant_scoped(tmp_path: Path) -> None:
    study = plan("Galway", "IE", ("dentist", "accountant"))
    store_study(tmp_path, "tenant-a", study)
    assert len(all_studies(tmp_path, "tenant-a")) == 1
    assert all_studies(tmp_path, "tenant-b") == []
    assert "Galway" in market_overview(tmp_path, "tenant-a")
    assert "dentist" in market_detail(study)
    assert b"veridra_market_review_input" in input_json(study)


def test_market_ids_are_path_safe(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="Invalid"):
        study_path(tmp_path, "tenant-a", "../../elsewhere")

def test_guided_sweep_skips_completed_sectors() -> None:
    study = plan("Galway", "IE", ("dentist", "accountant"))
    assert next_pending_sector(study) == "dentist"
    study.queries[0].status = "captured"
    assert next_pending_sector(study) == "accountant"
    assert "Continue: accountant" in market_detail(study)
    assert "Sector coverage" in sector_chart(study)
    study.queries[1].status = "captured"
    assert next_pending_sector(study) is None

def test_map_uses_only_real_observed_coordinates() -> None:
    assert _coordinates_from_maps_url("https://maps.google.com/maps/place/a/@53.2707,-9.0568,15z") is None
    assert _coordinates_from_maps_url("https://maps.google.com/maps/place/a/!3d53.2707!4d-9.0568") == (53.2707, -9.0568)
    assert _coordinates_from_maps_url("https://maps.google.com/maps/place/a") is None
    study = plan("Galway", "IE", ("dentist",))
    assert "No verified business coordinates" in geographic_overview(study)


def test_map_escapes_untrusted_business_name() -> None:
    from veridra.market_intelligence import add_observations
    from veridra.prospect_discovery import ObservedBusiness

    study = plan("Galway", "IE", ("dentist",))
    b = ObservedBusiness.model_validate({
        "provider": "google_maps",
        "provider_key": "google-maps:one",
        "name": "</script><script>alert(1)</script>",
        "country_code": "IE",
        "source_url": "https://maps.google.com/maps/place/a/!3d53.2707!4d-9.0568",
    })
    view = geographic_overview(add_observations(study, "dentist", [b]))
    assert "<iframe" in view
    assert "/map-view" in view
    assert "</script><script>alert(1)</script>" not in view


def test_market_kpis_are_readable_cards() -> None:
    study = plan("Galway", "IE", ("dentist",))
    content = market_detail(study)
    assert "market-kpis" in content
    assert "font-size:23px" in content
    assert "<span>Businesses</span>" in content


def test_workbench_layout_and_readable_type() -> None:
    study = plan("Galway", "IE", ("dentist", "accountant"))
    page = market_detail(study)
    assert "market-grid" in page
    assert "market-sector-plan" in page
    assert "market-map" in page
    assert "market-priorities" in page
    assert "<details class='market-bottom'>" in page
    assert "font:14px/1.45" in page
    assert "market-next" in page
    assert "overflow:auto" in page


def test_market_details_are_mutually_exclusive_tabs() -> None:
    study = plan("Galway", "IE", ("dentist",))
    page = market_detail(study)
    assert "market-tab-businesses" in page
    assert "market-tab-coverage" in page
    assert "market-tab-review" in page
    assert "type='radio'" in page
    assert ".market-bottom[open]{position:absolute" in page
    assert "market-tab-panels" in page


def test_search_plan_management_preserves_businesses_and_history() -> None:
    from veridra.market_intelligence import manage_queries

    study = plan("Galway", "IE", ("dentist", "solicitor"))
    original = study.queries[0].query_text
    updated = manage_queries(study, "edit", [], sector="dentist", query_text="dental care Galway")
    assert updated.queries[0].query_history == [original]
    assert updated.queries[0].query_text == "dental care Galway"
    assert updated.queries[0].status == "planned"
    updated = manage_queries(updated, "deactivate", ["solicitor"])
    assert not updated.queries[1].active
    updated = manage_queries(updated, "queue", ["dentist"])
    assert updated.batch_queue == ["dentist"]
    assert next_pending_sector(updated) == "dentist"
    updated = manage_queries(updated, "add", [], sector="chiropractor", query_text="chiropractor in Galway, IE")
    assert len(updated.queries) == 3
    updated = manage_queries(updated, "remove", ["dentist"])
    assert "dentist" not in [q.sector for q in updated.queries]
    assert updated.batch_queue == []


def test_bulk_controls_render_in_workbench() -> None:
    study = plan("Galway", "IE", ("dentist", "solicitor"))
    page = market_detail(study)
    assert "Queue selected" in page
    assert "Queue all" in page
    assert "market-tab-edit" in page
    assert "name='query_text'" in page
    assert "name='active'" in page
