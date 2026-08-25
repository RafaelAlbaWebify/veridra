from typing import cast

from veridra.assisted_google_maps import _profile_signals
from veridra.local_competitive_context_cli import _context_for, build_benchmark


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

    context = _context_for(rows[0], benchmark, {}, {})
    signals = cast(dict[str, object], context["signals"])
    assert signals["review_volume_vs_local_median"] == "stronger"
    assert "score" not in context
    strengths = cast(list[str], context["strengths"])
    assert any("review proof" in item for item in strengths)


def test_visual_evidence_becomes_business_facing_competitive_gap() -> None:
    row: dict[str, object] = {
        "name": "Clinic A",
        "website": "https://a.ie",
        "rating": 4.8,
        "review_count": 200,
        "profile_photo_signal_count": 5,
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
