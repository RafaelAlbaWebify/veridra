from __future__ import annotations

import pytest

from veridra.assisted_discovery_acceptance_cli import build_parser, build_start_url


def test_build_start_url_encodes_query_without_changing_meaning() -> None:
    url = build_start_url("dentist in Vigo, ES")
    assert url == (
        "https://www.google.com/maps/search/?api=1&query=dentist+in+Vigo%2C+ES"
    )


def test_build_start_url_rejects_blank_query() -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        build_start_url("   ")


def test_acceptance_parser_keeps_bounded_defaults() -> None:
    args = build_parser().parse_args(
        [
            "--query",
            "dentist in Vigo, ES",
            "--country-code",
            "ES",
            "--locality",
            "Vigo",
        ]
    )

    assert args.max_results == 8
    assert args.max_scrolls == 5
    assert args.max_seconds == 30.0
    assert args.max_stagnant_scrolls == 2
