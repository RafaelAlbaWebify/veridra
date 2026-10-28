from veridra.agency_navigation import _NAV_HELP


def test_website_care_navigation_has_help_copy() -> None:
    assert "website-care" in _NAV_HELP
    assert "maintenance evidence" in _NAV_HELP["website-care"]
