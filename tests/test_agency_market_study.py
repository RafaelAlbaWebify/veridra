from __future__ import annotations

from pathlib import Path

from veridra.agency_market_study import (
    all_studies,
    input_json,
    market_detail,
    market_overview,
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
