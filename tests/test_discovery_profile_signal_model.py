from veridra.prospect_discovery import ObservedBusiness


def test_observed_business_accepts_optional_local_profile_signals() -> None:
    business = ObservedBusiness.model_validate(
        {
            "provider": "assisted-google-maps",
            "provider_key": "maps:test",
            "name": "Clinic",
            "country_code": "IE",
            "rating": 4.8,
            "review_count": 123,
            "profile_photo_signal_count": 7,
        }
    )
    assert business.rating == 4.8
    assert business.review_count == 123
    assert business.profile_photo_signal_count == 7
