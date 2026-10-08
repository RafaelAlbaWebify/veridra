# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path

import pytest

from veridra.market_intelligence import (
    add_observations,
    dashboard,
    import_review,
    load,
    plan,
    save,
    snapshot,
    snapshot_hash,
)
from veridra.prospect_discovery import ObservedBusiness


def business(name: str = "Clinic One", *, website: str | None = None, key: str = "google-maps:abc") -> ObservedBusiness:
    return ObservedBusiness.model_validate({
        "provider": "google_maps", "provider_key": key, "name": name,
        "category": "Dentist", "locality": "Galway", "country_code": "IE",
        "website": website, "source_url": "https://www.google.com/maps/place/example",
        "review_count": 50,
    })


def test_market_plan_ingest_revisit_and_resume(tmp_path: Path) -> None:
    path = tmp_path / "study.json"
    study = plan("Galway", "ie", ("dentist", "accountant"))
    study = add_observations(study, "dentist", [business()])
    study = add_observations(study, "accountant", [business(website="https://example.org")])
    assert len(study.businesses) == 1
    assert set(study.businesses[0].query_sectors) == {"dentist", "accountant"}
    assert str(study.businesses[0].business.website) == "https://example.org/"
    save(study, path)
    restored = load(path)
    assert len(restored.businesses) == 1
    assert snapshot(restored)["coverage"]["captured_queries"] == 2
    assert "Clinic One" in dashboard(restored)


def test_review_rejects_stale_and_unknown_target() -> None:
    study = add_observations(plan("Galway", "IE", ("dentist",)), "dentist", [business()])
    base = {
        "contract": "veridra_market_review_output",
        "schema_version": "1.0",
        "study_id": study.study_id,
        "snapshot_sha256": snapshot_hash(study),
        "summary": "Focus on verified issues, not presumed revenue.",
        "sector_priorities": [{"sector": "dentist", "priority": 80, "reason": "Initial sample"}],
        "candidate_priorities": [],
    }
    assert import_review(study, base).review is not None
    with pytest.raises(ValueError, match="stale"):
        import_review(study, {**base, "snapshot_sha256": "stale"})
    with pytest.raises(ValueError, match="Unknown target"):
        import_review(study, {**base, "sector_priorities": [{"sector": "unknown", "priority": 80, "reason": "x"}]})
    assert add_observations(import_review(study, base), "dentist", []).review is None


def test_no_auto_merge_when_only_name_matches() -> None:
    study = plan("Galway", "IE", ("dentist",))
    one = business(key="google-maps:one")
    two = business(key="google-maps:two")
    study = add_observations(study, "dentist", [one, two])
    assert len(study.businesses) == 2


def test_html_is_escaped() -> None:
    study = plan("<script>alert(1)</script>", "IE", ("dentist",))
    page = dashboard(study)
    assert "&lt;script&gt;" in page
    assert "<script>alert(1)</script>" not in page
