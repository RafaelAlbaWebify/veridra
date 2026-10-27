import json
import sqlite3

import pytest

from veridra.website_care_evidence import import_evidence, normalize


def sample():
    return {
        "contract": "webify_wordpress_care_cycle_v1",
        "passed": True,
        "started_utc": "2026-10-27T15:25:46+00:00",
        "finished_utc": "2026-10-27T15:27:11+00:00",
        "steps": {"inspect": "PASS", "backup": "PASS", "isolated_restore": "PASS"},
    }


def test_import_idempotent_and_private(tmp_path):
    evidence = tmp_path / "input.json"
    evidence.write_text(json.dumps(sample()), encoding="utf-8")
    db = tmp_path / "care.sqlite"
    assert import_evidence(evidence, db, "lab-wp-8088", "wordpress")
    assert not import_evidence(evidence, db, "lab-wp-8088", "wordpress")
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT website_ref, platform, passed FROM care_runs"
        ).fetchall()
    assert rows == [("lab-wp-8088", "wordpress", 1)]


@pytest.mark.parametrize(
    "change",
    [
        {"contract": "unknown"},
        {"passed": False},
        {"steps": {"inspect": "PASS", "backup": "FAIL", "isolated_restore": "PASS"}},
        {"started_utc": "2026-10-27T20:00:00+00:00"},
        {"started_utc": "not-a-timestamp"},
    ],
)
def test_reject_inconsistent_input(change):
    data = sample()
    data.update(change)
    with pytest.raises(ValueError):
        normalize(data, website_ref="lab-wp-8088", platform="wordpress")


def test_reject_other_platform_for_wordpress_contract():
    with pytest.raises(ValueError):
        normalize(sample(), website_ref="static-site", platform="static")
