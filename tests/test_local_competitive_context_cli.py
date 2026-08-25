from pathlib import Path
from typing import cast

from veridra.assisted_google_maps import _profile_signals
from veridra.local_competitive_context_cli import (
    _context_for,
    _merge_rows,
    build_benchmark,
)


def test_profile_signals_extract_rating_and_review_volume() -> None:
    assert _profile_signals("Phoenix Dental 4.8 (1,234) Dentist") == (4.8, 1234)
    assert _profile_signals("D4 Dentist 4.6 stars 87 reviews") == (4.6, 87)
    assert _profile_signals("No reputation signal") == (None, None)


def test_relative_context_uses_local_medians_without_global_score() -> None:
    rows: list[dict[str, object]] = [
        {
            "name": "Clinic A",
            "website": "https://a.ie",
            "rating": 4.9,
            "review_count": 400,
            "profile_photo_signal_count": 10,
        },
        {
            "name": "Clinic B",
            "website": "https://b.ie",
            "rating": 4.5,
            "review_count": 100,
            "profile_photo_signal_count": 4,
        },
        {
            "name": "Clinic C",
            "website": "https://c.ie",
            "rating": 4.7,
            "review_count": 200,
            "profile_photo_signal_count": 6,
        },
    ]
    benchmark = build_benchmark(rows)
    assert benchmark["rating_median"] == 4.7
    assert benchmark["review_count_median"] == 200.0
    assert benchmark["photo_metric_status"] == "suppressed"

    context = _context_for(rows[0], benchmark, {}, {})
    signals = cast(dict[str, object], context["signals"])
    assert signals["review_volume_vs_local_median"] == "stronger"
    assert signals["photo_metric"] == "suppressed"
    assert "score" not in context
    strengths = cast(list[str], context["strengths"])
    assert any("review proof" in item for item in strengths)


def test_low_review_volume_is_context_not_unsupported_webify_opportunity() -> None:
    rows: list[dict[str, object]] = [
        {
            "name": "Low Reviews Dental",
            "website": "https://low.ie",
            "rating": 4.6,
            "review_count": 10,
        },
        {
            "name": "High Reviews Dental",
            "website": "https://high.ie",
            "rating": 4.9,
            "review_count": 400,
        },
    ]
    benchmark = build_benchmark(rows)
    context = _context_for(rows[0], benchmark, {}, {})
    gaps = cast(list[str], context["competitive_gaps"])
    opportunities = cast(list[str], context["webify_opportunities"])

    assert any("less review proof" in item for item in gaps)
    assert opportunities == []


def test_visual_evidence_becomes_business_facing_competitive_gap() -> None:
    row: dict[str, object] = {
        "name": "Clinic A",
        "website": "https://a.ie",
        "rating": 4.8,
        "review_count": 200,
    }
    benchmark = build_benchmark([row])
    visual: dict[str, list[dict[str, object]]] = {
        "a.ie": [
            {
                "issue_type": "mobile_overflow",
                "what_we_noticed": "Part of this page extends beyond a normal phone screen.",
            }
        ]
    }
    context = _context_for(row, benchmark, {}, visual)
    gaps = cast(list[str], context["competitive_gaps"])
    opportunities = cast(list[str], context["webify_opportunities"])
    assert any("Website evidence" in item for item in gaps)
    assert any("mobile presentation" in item for item in opportunities)


def test_multi_query_rows_are_deduped_and_source_files_are_retained() -> None:
    sources = [
        (
            Path("dentist.zip"),
            [
                {
                    "name": "Phoenix Dental",
                    "provider_key": "phoenix",
                    "website": "",
                    "rating": 4.7,
                    "review_count": 80,
                }
            ],
        ),
        (
            Path("dental-clinic.zip"),
            [
                {
                    "name": "Phoenix Dental",
                    "provider_key": "phoenix",
                    "website": "https://phoenixdental.ie",
                    "rating": 4.7,
                    "review_count": 80,
                },
                {
                    "name": "D4 Dentist",
                    "provider_key": "d4",
                    "website": "https://d4dentist.ie",
                    "rating": 4.9,
                    "review_count": 120,
                },
            ],
        ),
    ]

    merged = _merge_rows(sources)

    assert len(merged) == 2
    phoenix = merged[0]
    assert phoenix["website"] == "https://phoenixdental.ie"
    assert phoenix["source_discovery_files"] == ["dentist.zip", "dental-clinic.zip"]
