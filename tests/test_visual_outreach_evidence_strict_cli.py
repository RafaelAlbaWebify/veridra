from __future__ import annotations

import json
import zipfile
from pathlib import Path

from veridra.visual_outreach_evidence_strict_cli import _html_summary, _load, _safe_stem


def test_safe_stem_is_bounded() -> None:
    value = _safe_stem("Clinic & Dental / Dublin")
    assert value == "Clinic-Dental-Dublin"
    assert len(_safe_stem("x" * 200)) <= 72


def test_strict_summary_is_plain_language() -> None:
    output = _html_summary(
        [
            {
                "business_name": "Clinic A",
                "evidence": [
                    {
                        "screenshot_path": "01-Clinic-A/01-dead-end.png",
                        "what_we_noticed": (
                            "The visible link ‘Book now’ leads to a page that does not work."
                        ),
                        "why_it_matters": (
                            "A visitor can hit a dead end while trying to continue through "
                            "the website."
                        ),
                        "page_url": "https://clinic.example/",
                    }
                ],
            }
        ]
    )
    assert "Book now" in output
    assert "01-Clinic-A/01-dead-end.png" in output
    assert "Content-Security-Policy" not in output
    assert "aria-label" not in output


def test_strict_summary_marks_no_visual_issue() -> None:
    output = _html_summary([{"business_name": "Clinic B", "evidence": []}])
    assert "No strong screenshot-ready issue captured." in output



def test_rank_index_keeps_first_archive_entry_and_ranking_order(tmp_path: Path) -> None:
    path = tmp_path / "audits.zip"
    rows = [
        {"result_rank": 12, "name": "Twelve", "audit_status": "success"},
        {"result_rank": 2, "name": "Two", "audit_status": "success"},
        {"result_rank": 5, "name": "Failed", "audit_status": "failed"},
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("audit_ranking.json", json.dumps(rows))
        archive.writestr("assessments/02-first.json", json.dumps({"marker": "first"}))
        archive.writestr("assessments/02-second.json", json.dumps({"marker": "second"}))
        archive.writestr("assessments/12-twelve.json", json.dumps({"marker": "twelve"}))
        archive.writestr("other/02-irrelevant.json", json.dumps({}))
    values = _load(path, max_businesses=10)
    assert [row.result_rank for row in values] == [12, 2]
    assert values[0].assessment["marker"] == "twelve"
    assert values[1].assessment["marker"] == "first"
