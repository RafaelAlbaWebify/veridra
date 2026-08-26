from datetime import UTC, datetime

from veridra.review_intelligence_cli import (
    _candidate_rows,
    _merge_reviews,
    _rating_from_label,
    _relative_date,
    _stable_review_id,
    _statistics,
)


def test_relative_dates_are_approximated_from_observation_time() -> None:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
    assert _relative_date("2 weeks ago", observed_at=now) == "2026-08-12"
    assert _relative_date("a month ago", observed_at=now) == "2026-07-27"
    assert _relative_date("Edited 3 days ago", observed_at=now) == "2026-08-23"
    assert _relative_date("unknown", observed_at=now) is None


def test_rating_parser_uses_google_star_label() -> None:
    assert _rating_from_label("5 stars") == 5
    assert _rating_from_label("Rated 3.0 stars") == 3
    assert _rating_from_label("No rating") is None


def test_review_id_is_stable() -> None:
    first = _stable_review_id(
        business_name="Example Dental",
        source_review_id="abc123",
        text="Great clinic",
        rating=5,
    )
    second = _stable_review_id(
        business_name="Example Dental",
        source_review_id="abc123",
        text="Changed text",
        rating=4,
    )
    assert first == second
    assert first.startswith("review:Example-Dental:")


def test_merge_reviews_tracks_multiple_sampling_strategies() -> None:
    base = {
        "evidence_id": "review:Clinic:1",
        "rating": 5,
        "text": "Helpful",
        "owner_response_present": False,
    }
    merged = _merge_reviews(
        [
            [{**base, "sample_strategy": "newest"}],
            [{**base, "sample_strategy": "highest"}],
        ]
    )
    assert len(merged) == 1
    assert merged[0]["sample_strategies"] == ["newest", "highest"]


def test_statistics_are_explicitly_sample_scoped() -> None:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
    reviews = [
        {
            "rating": 2,
            "approximate_review_date": "2026-08-20",
            "owner_response_present": True,
        },
        {
            "rating": 5,
            "approximate_review_date": "2026-07-01",
            "owner_response_present": False,
        },
        {
            "rating": 4,
            "approximate_review_date": "2025-01-01",
            "owner_response_present": False,
        },
    ]
    stats = _statistics(reviews, now=now)
    assert stats["sample_size"] == 3
    assert stats["sampled_reviews_last_30_days"] == 1
    assert stats["sampled_reviews_last_90_days"] == 2
    assert stats["sampled_reviews_last_365_days"] == 2
    assert stats["owner_response_rate_sample"] == 0.333
    assert stats["negative_review_response_rate_sample"] == 1.0
    assert "bounded sample" in str(stats["scope_note"])


def test_candidate_selection_prioritizes_webify_evidence() -> None:
    rows = [
        {
            "business_name": "Ordinary Clinic",
            "source_url": "https://www.google.com/maps/place/ordinary",
            "webify_opportunities": [],
            "website_visual_evidence_count": 0,
        },
        {
            "business_name": "Evidence Clinic",
            "source_url": "https://www.google.com/maps/place/evidence",
            "webify_opportunities": ["Fix mobile layout"],
            "website_visual_evidence_count": 1,
        },
        {
            "business_name": "No Maps Source",
            "source_url": "https://example.com/",
            "webify_opportunities": ["Something"],
            "website_visual_evidence_count": 2,
        },
    ]
    selected = _candidate_rows(rows, 2)
    assert [row["business_name"] for row in selected] == ["Evidence Clinic", "Ordinary Clinic"]
