from __future__ import annotations

from veridra.gbp_profile_evidence import (
    GbpProfileEvidence,
    classify_booking_links,
    external_http_url,
    hours_from_action_labels,
    unique_external_links,
)


def test_external_http_url_rejects_google_navigation() -> None:
    assert external_http_url("https://www.google.com/maps/place/example") is None
    assert external_http_url("https://lh5.googleusercontent.com/image") is None
    assert external_http_url("https://clinic.example/book") == "https://clinic.example/book"


def test_booking_links_require_external_url_and_booking_signal() -> None:
    links = [
        ("https://clinic.example/book", "Book an appointment", "appointment"),
        ("https://clinic.example/about", "About us", "authority"),
        ("https://www.google.com/maps/dir/", "Directions", "directions"),
    ]

    assert classify_booking_links(links) == ("https://clinic.example/book",)
    assert unique_external_links(links) == (
        "https://clinic.example/book",
        "https://clinic.example/about",
    )


def test_hours_from_action_labels_keeps_visible_day_rows_only() -> None:
    labels = (
        "Thursday, 8 am to 8 pm, Copy open hours",
        "Friday, 8 am to 8 pm, Copy open hours",
        "Website: clinic.example",
        "Thursday, 8 am to 8 pm, Copy open hours",
    )

    assert hours_from_action_labels(labels) == (
        "Thursday, 8 am to 8 pm | Friday, 8 am to 8 pm"
    )


def test_profile_evidence_keeps_absence_as_observation_not_claim() -> None:
    evidence = GbpProfileEvidence.model_validate(
        {
            "business_name": "Example Clinic",
            "source_url": "https://www.google.com/maps/place/example",
            "address_text": "",
            "phone_text": "",
            "hours_text": "",
        }
    )

    assert evidence.address_text == ""
    assert "not by itself proof" in evidence.coverage_note
    assert evidence.collection_status == "ok"
