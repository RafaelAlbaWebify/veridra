from __future__ import annotations

import json
import zipfile
from pathlib import Path

from veridra.visual_outreach_evidence_cli import (
    _affected_urls,
    _broken_targets,
    _canonical_http_url,
    _html_summary,
    _load_business_audits,
    _plain_text,
)


def test_canonical_http_url_normalizes_host_and_drops_fragment() -> None:
    assert (
        _canonical_http_url("HTTPS://Example.IE/contact?x=1#section")
        == "https://example.ie/contact?x=1"
    )


def test_plain_text_is_business_facing() -> None:
    noticed, impact = _plain_text("broken_link")
    assert "does not work" in noticed
    assert "dead end" in impact
    combined = f"{noticed} {impact}".casefold()
    assert "http" not in combined
    assert "status code" not in combined


def test_extracts_only_http_affected_urls_and_broken_targets() -> None:
    form = {
        "evidence": {
            "affected_urls": [
                "https://clinic.ie/contact",
                "mailto:test@clinic.ie",
                3,
            ]
        }
    }
    assert _affected_urls(form) == ["https://clinic.ie/contact"]

    broken = {
        "evidence": {
            "broken_targets": [
                {"target_url": "https://clinic.ie/missing", "status_code": 404},
                "bad",
            ]
        }
    }
    assert _broken_targets(broken) == [
        {"target_url": "https://clinic.ie/missing", "status_code": 404}
    ]


def test_load_business_audits_uses_success_rows_only(tmp_path: Path) -> None:
    path = tmp_path / "VERIDRA_PROSPECT_AUDITS_test.zip"
    ranking = [
        {
            "result_rank": 5,
            "name": "Clinic A",
            "audit_url": "https://clinic-a.ie/",
            "audit_status": "success",
        },
        {
            "result_rank": 6,
            "name": "Clinic B",
            "audit_url": "https://clinic-b.ie/",
            "audit_status": "failed",
        },
    ]
    assessment = {
        "target": "https://clinic-a.ie/",
        "findings": [
            {
                "id": "crawl.broken-internal-links",
                "evidence": {
                    "broken_targets": [
                        {
                            "target_url": "https://clinic-a.ie/missing",
                            "source_urls": ["https://clinic-a.ie/"],
                            "status_code": 404,
                        }
                    ]
                },
            }
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("audit_ranking.json", json.dumps(ranking))
        archive.writestr("assessments/05-Clinic-A.json", json.dumps(assessment))

    values = _load_business_audits(path, max_businesses=15)
    assert len(values) == 1
    assert values[0].name == "Clinic A"
    assert values[0].result_rank == 5


def test_html_summary_uses_plain_language_and_screenshot_path() -> None:
    result = _html_summary(
        [
            {
                "business_name": "Clinic A",
                "evidence": [
                    {
                        "screenshot_path": "05-Clinic-A/01-broken-link.png",
                        "what_we_noticed": "This link sends visitors to a page that does not work.",
                        "why_it_matters": "A dead end can interrupt a visitor.",
                        "page_url": "https://clinic-a.ie/",
                    }
                ],
            }
        ]
    )
    assert "05-Clinic-A/01-broken-link.png" in result
    assert "This link sends visitors" in result
    assert "technical_finding_weight" not in result
    assert "Content-Security-Policy" not in result
