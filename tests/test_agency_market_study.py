from __future__ import annotations

from pathlib import Path

from veridra.agency_market_study import (
    _coordinates_from_maps_url,
    geographic_overview,
    all_studies,
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
    assert "Continue with next sector: accountant" in market_detail(study)
    assert "Sector coverage" in sector_chart(study)
    study.queries[1].status = "captured"
    assert next_pending_sector(study) is None

def test_map_uses_only_real_observed_coordinates() -> None:
    assert _coordinates_from_maps_url("https://maps.google.com/maps/place/a/@53.2707,-9.0568,15z") == (53.2707, -9.0568)
    assert _coordinates_from_maps_url("https://maps.google.com/maps/place/a/!3d53.2707!4d-9.0568") == (53.2707, -9.0568)
    assert _coordinates_from_maps_url("https://maps.google.com/maps/place/a") is None
    study = plan("Galway", "IE", ("dentist",))
    assert "No verified coordinates available" in geographic_overview(study)


def test_map_escapes_untrusted_business_name() -> None:
    from veridra.market_intelligence import add_observations
    from veridra.prospect_discovery import ObservedBusiness

    study = plan("Galway", "IE", ("dentist",))
    b = ObservedBusiness.model_validate({
        "provider": "google_maps",
        "provider_key": "google-maps:one",
        "name": "</script><script>alert(1)</script>",
        "country_code": "IE",
        "source_url": "https://maps.google.com/maps/place/a/@53.2707,-9.0568,15z",
    })
    view = geographic_overview(add_observations(study, "dentist", [b]))
    assert "market-map" in view
    assert "</script><script>alert(1)</script>" not in view
