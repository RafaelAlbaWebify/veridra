import json

import pytest

from veridra.website_care_evidence import import_evidence
from veridra.website_care_history import read_history


def test_history_is_read_only_and_filterable(tmp_path):
    database = tmp_path / "care.db"
    assert read_history(database) == []
    payload = {
        "contract": "webify_wordpress_care_cycle_v1",
        "started_utc": "2026-10-27T15:25:46+00:00",
        "finished_utc": "2026-10-27T15:27:11+00:00",
        "steps": {"inspect": "PASS", "backup": "PASS", "isolated_restore": "PASS"},
        "passed": True,
    }
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    assert import_evidence(evidence, database, "lab-site", "wordpress")
    rows = read_history(database, website_ref="lab-site")
    assert len(rows) == 1
    assert rows[0]["passed"] == 1
    assert rows[0]["platform"] == "wordpress"
    assert read_history(database, website_ref="other-site") == []


@pytest.mark.parametrize("limit", [0, 201])
def test_history_bounds(tmp_path, limit):
    with pytest.raises(ValueError):
        read_history(tmp_path / "not-found.db", limit=limit)
