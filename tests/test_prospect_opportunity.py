from veridra.prospect_discovery import ObservedBusiness
from veridra.prospect_opportunity import OpportunityBand, assess_opportunity


def _business(**updates: object) -> ObservedBusiness:
    payload: dict[str, object] = {
        "provider": "assisted-google-maps",
        "provider_key": "google-maps:test",
        "name": "Example Dental",
        "country_code": "IE",
        "website": "https://example.ie",
        "rating": 4.8,
        "review_count": 80,
        "profile_photo_signal_count": 8,
    }
    payload.update(updates)
    return ObservedBusiness.model_validate(payload)


def test_missing_website_with_real_activity_is_priority() -> None:
    assessment = assess_opportunity(
        _business(website=None, review_count=80, profile_photo_signal_count=2)
    )

    assert assessment.band is OpportunityBand.priority
    assert assessment.score == 77
    assert assessment.digital_gap_score == 53
    assert assessment.business_activity_score == 24
    assert any("No business website" in reason for reason in assessment.reasons)


def test_missing_website_without_activity_is_not_promoted_to_priority() -> None:
    assessment = assess_opportunity(
        _business(
            website=None,
            rating=None,
            review_count=0,
            profile_photo_signal_count=0,
        )
    )

    assert assessment.score == 70
    assert assessment.band is OpportunityBand.medium
    assert assessment.business_activity_score == 0


def test_mature_digital_presence_is_low_opportunity() -> None:
    assessment = assess_opportunity(_business())

    assert assessment.band is OpportunityBand.low
    assert assessment.digital_gap_score == 0
    assert assessment.business_activity_score == 24
    assert assessment.score == 24


def test_sparse_reviews_and_photos_can_be_high_opportunity() -> None:
    assessment = assess_opportunity(
        _business(review_count=8, profile_photo_signal_count=1)
    )

    assert assessment.digital_gap_score == 20
    assert assessment.business_activity_score == 12
    assert assessment.score == 32
    assert assessment.band is OpportunityBand.medium


def test_low_rating_does_not_add_opportunity_points() -> None:
    strong = assess_opportunity(_business(rating=4.8, review_count=80))
    weak_rating = assess_opportunity(_business(rating=3.8, review_count=80))

    assert weak_rating.score == strong.score
    assert weak_rating.band is strong.band
    assert any("not treated as a Webify-fixable" in reason for reason in weak_rating.reasons)
