from __future__ import annotations

from veridra.assisted_google_maps import (
    _canonical_maps_identity,
    _clean_category,
    _external_website,
    _provider_key,
)


def test_same_google_place_identity_survives_url_variants() -> None:
    sponsored = (
        "https://www.google.com/maps/place/Slievemore+Dental/"
        "data=!4m7!3m6!1s0x4867091e23065b7f:0x433908020e736b82!8m2!3d53.2924936!4d-6.2010661"
        "?authuser=0&hl=en&rclk=1"
    )
    organic = (
        "https://www.google.com/maps/place/Slievemore+Dental/"
        "data=!4m7!3m6!1s0x4867091e23065b7f:0x433908020e736b82!8m2!3d53.2924936!4d-6.2010661"
        "?entry=ttu&g_ep=test"
    )

    assert _canonical_maps_identity(sponsored, name="Slievemore Dental") == _canonical_maps_identity(
        organic,
        name="Slievemore Dental",
    )
    assert _provider_key(sponsored, name="Slievemore Dental") == _provider_key(
        organic,
        name="Slievemore Dental",
    )


def test_google_redirect_can_reveal_real_external_website() -> None:
    wrapped = "https://www.google.com/url?q=https%3A%2F%2Fslievemoredental.ie%2F&sa=U"

    assert _external_website(wrapped) == "https://slievemoredental.ie/"
    assert _external_website("https://www.google.ie/maps/place/example") is None


def test_category_cleanup_rejects_non_categories() -> None:
    assert _clean_category("Slievemore Dental", name="Slievemore Dental") == ""
    assert _clean_category("Sponsored", name="Slievemore Dental") == ""
    assert _clean_category("  Emergency dental service  ", name="Slievemore Dental") == (
        "Emergency dental service"
    )
