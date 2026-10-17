from __future__ import annotations

import pytest

from veridra.assisted_google_maps import _is_supported_maps_page


@pytest.mark.parametrize("url", [
    "https://www.google.es/maps/search/dentist+vigo",
    "https://google.com/maps",
    "https://maps.google.com/maps/place/a",
    "https://www.google.co.uk/maps/search/x",
])
def test_accepts_recognized_google_maps_origins(url: str) -> None:
    assert _is_supported_maps_page(url)


@pytest.mark.parametrize("url", [
    "https://evil.example/path/google.com/maps",
    "https://google.com.evil.example/maps",
    "https://evilgoogle.es/maps",
    "https://google.evil/maps",
    "https://www.google.es.evil/maps",
    "http://www.google.es/maps",
    "https://www.google.es.evil/maps?q=https://google.es/maps",
    "https://www.google.es/other?next=/maps",
    "https://user:password@www.google.es/maps",
])
def test_rejects_lookalike_and_non_maps_pages(url: str) -> None:
    assert not _is_supported_maps_page(url)
