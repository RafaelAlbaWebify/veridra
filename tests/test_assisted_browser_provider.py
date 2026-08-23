from __future__ import annotations

from io import StringIO

import pytest

from veridra.assisted_browser_protocol import (
    BrowserProtocolError,
    ProtocolRequest,
    ProtocolResponse,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
    write_message,
)
from veridra.assisted_browser_provider import SubprocessPlaywrightDiscoveryProvider
from veridra.assisted_discovery import BoundedDiscoveryLimits, TraversalStopReason
from veridra.assisted_google_maps import capture_visible_google_maps_businesses


class _Link:
    def __init__(self, href: str) -> None:
        self.href = href

    def get_attribute(self, name: str) -> str | None:
        return self.href if name == "href" else None


class _Links:
    def __init__(self, hrefs: list[str]) -> None:
        self.links = [_Link(item) for item in hrefs]

    def count(self) -> int:
        return len(self.links)

    def nth(self, index: int) -> _Link:
        return self.links[index]


class _Card:
    def __init__(self, text: str, hrefs: list[str]) -> None:
        self.text = text
        self.hrefs = hrefs

    def inner_text(self, *, timeout: int) -> str:
        assert timeout == 2_000
        return self.text

    def locator(self, selector: str) -> _Links:
        assert selector == "a[href]"
        return _Links(self.hrefs)


class _Cards:
    def __init__(self, cards: list[_Card]) -> None:
        self.cards = cards

    def count(self) -> int:
        return len(self.cards)

    def nth(self, index: int) -> _Card:
        return self.cards[index]


class _Page:
    url = "https://www.google.es/maps/search/dentist+vigo"

    def __init__(self) -> None:
        self.cards = _Cards(
            [
                _Card(
                    "Vigo Dental Clinic\nDental clinic\n4.8 stars",
                    [
                        "https://www.google.es/maps/place/Vigo+Dental+Clinic/data=abc",
                        "https://clinic.example/",
                    ],
                )
            ]
        )

    def locator(self, selector: str) -> _Cards:
        assert selector == '[role="feed"] [role="article"]'
        return self.cards


def test_protocol_round_trip_and_request_id_validation() -> None:
    encoded = encode_request(
        ProtocolRequest(
            request_id="request-1",
            command="collect_bounded",
            payload={"max_results": 10},
        )
    )
    decoded = decode_request(encoded)
    assert decoded.request_id == "request-1"
    assert decoded.command == "collect_bounded"
    assert decoded.payload == {"max_results": 10}

    response = encode_response(
        ProtocolResponse(
            request_id="request-1",
            ok=True,
            result={"businesses": []},
        )
    )
    assert decode_response(response, expected_request_id="request-1").ok is True
    with pytest.raises(BrowserProtocolError, match="request_id mismatch"):
        decode_response(response, expected_request_id="different-request")


def test_protocol_write_flushes_bounded_message() -> None:
    stream = StringIO()
    write_message(stream, encode_response(ProtocolResponse(request_id="r1", ok=True)))
    assert '"request_id":"r1"' in stream.getvalue()


def test_google_maps_capture_uses_explicit_territory_context() -> None:
    records = capture_visible_google_maps_businesses(
        _Page(),
        max_results=5,
        country_code="es",
        locality="Vigo",
        administrative_area="Pontevedra",
    )

    assert len(records) == 1
    record = records[0]
    assert record.name == "Vigo Dental Clinic"
    assert record.category == "Dental clinic"
    assert record.country_code == "ES"
    assert record.locality == "Vigo"
    assert record.administrative_area == "Pontevedra"
    assert record.provider == "assisted-google-maps"
    assert record.provider_key.startswith("google-maps:")
    assert len(record.provider_key) < 100
    assert str(record.website) == "https://clinic.example/"
    assert "/maps/place/" in str(record.source_url)


def test_parent_decodes_bounded_child_result() -> None:
    provider = SubprocessPlaywrightDiscoveryProvider(country_code="ES", locality="Vigo")
    raw = {
        "businesses": [
            {
                "provider": "assisted-google-maps",
                "provider_key": "google-maps:abc",
                "name": "Vigo Dental Clinic",
                "category": "Dental clinic",
                "locality": "Vigo",
                "administrative_area": "Pontevedra",
                "country_code": "ES",
                "postal_area": "",
                "website": "https://clinic.example/",
                "phone": "",
                "source_url": "https://www.google.es/maps/place/Vigo+Dental+Clinic",
                "observed_at": "2026-08-23T12:00:00Z",
            }
        ],
        "observations": [
            {
                "query_text": "dentist in Vigo, ES",
                "query_sequence": 1,
                "result_rank": 1,
                "first_seen_scroll_step": 0,
            }
        ],
        "progress": {
            "query_text": "dentist in Vigo, ES",
            "query_sequence": 1,
            "scroll_step": 0,
            "unique_results": 1,
            "stagnant_scrolls": 0,
            "elapsed_seconds": 0.2,
            "stop_reason": "end_of_list",
        },
    }

    result = provider._decode_result(raw, limits=BoundedDiscoveryLimits(max_results=10))

    assert len(result.observations) == 1
    assert result.observations[0].business.country_code == "ES"
    assert result.observations[0].result_rank == 1
    assert result.progress.stop_reason is TraversalStopReason.end_of_list


def test_parent_rejects_child_result_above_server_limit() -> None:
    provider = SubprocessPlaywrightDiscoveryProvider(country_code="ES")
    business = {
        "provider": "assisted-google-maps",
        "provider_key": "google-maps:abc",
        "name": "Business",
        "country_code": "ES",
    }
    raw = {
        "businesses": [business, {**business, "provider_key": "google-maps:def"}],
        "observations": [{}, {}],
        "progress": {},
    }

    with pytest.raises(BrowserProtocolError, match="exceeded the configured result limit"):
        provider._decode_result(raw, limits=BoundedDiscoveryLimits(max_results=1))
