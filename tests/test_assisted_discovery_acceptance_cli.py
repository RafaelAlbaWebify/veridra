from __future__ import annotations

import pytest

from veridra import assisted_discovery_acceptance_cli as acceptance
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


@pytest.mark.parametrize(("count", "expected_code"), [(0, 1), (1, 0)])
def test_automatic_live_capture_fails_closed_without_results(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    count: int,
    expected_code: int,
) -> None:
    from types import SimpleNamespace

    events: list[str] = []

    class FakeManager:
        def __init__(self, _provider: object) -> None:
            pass

        def launch(self, **_kwargs: object) -> SimpleNamespace:
            events.append("launch")
            return SimpleNamespace(session_id="session-1")

        def mark_ready(self, _session_id: str) -> SimpleNamespace:
            events.append("ready")
            return SimpleNamespace(session_id="session-1")

        def collect(self, _session_id: str, *, limits: object) -> SimpleNamespace:
            events.append("collect")
            assert limits is not None
            observations = [
                SimpleNamespace(
                    result_rank=1,
                    business=SimpleNamespace(
                        name="Example Dental",
                        category="Dentist",
                        website=None,
                        source_url=None,
                        provider_key="test-1",
                        country_code="ES",
                        locality="Vigo",
                        administrative_area="Pontevedra",
                    ),
                    first_seen_scroll_step=0,
                )
            ][:count]
            return SimpleNamespace(
                session_id="session-1",
                state=SimpleNamespace(value="review"),
                query_text="dentist Vigo",
                observations=observations,
                progress=None,
            )

        def stop(self, _session_id: str) -> None:
            events.append("stop")

    class FakeProvider:
        def maps_results_ready(self) -> bool:
            events.append("status")
            return True

    monkeypatch.setattr(
        acceptance, "SubprocessPlaywrightDiscoveryProvider", lambda **_kw: FakeProvider()
    )
    monkeypatch.setattr(acceptance, "AssistedDiscoveryManager", FakeManager)
    monkeypatch.setattr(
        "veridra.assisted_discovery_acceptance_cli.time.sleep",
        lambda _n: events.append("settle"),
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a: pytest.fail("Automatic mode must not prompt the operator."),
    )

    assert acceptance.run([
        "--query", "dentist Vigo", "--country-code", "ES",
        "--automatic", "--settle-seconds", "0",
    ]) == expected_code
    assert events == ["launch", "settle", "status", "ready", "collect", "stop"]
    assert f'"acceptance_passed": {str(bool(count)).lower()}' in capsys.readouterr().out


def test_automatic_settle_seconds_bounds_are_checked() -> None:
    for seconds in ("-1", "31"):
        with pytest.raises(ValueError, match="settle-seconds must be between"):
            acceptance.run([
                "--query", "dentist Vigo", "--country-code", "ES",
                "--automatic", "--settle-seconds", seconds,
            ])


def test_automatic_login_waits_for_real_maps_feed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from types import SimpleNamespace

    events: list[str] = []

    class FakeProvider:
        def maps_results_ready(self) -> bool:
            events.append("status")
            return events.count("status") == 3

    class FakeManager:
        def __init__(self, _provider: object) -> None:
            pass

        def launch(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(session_id="one")

        def mark_ready(self, _session_id: str) -> SimpleNamespace:
            events.append("ready")
            return SimpleNamespace(session_id="one")

        def collect(self, _session_id: str, *, limits: object) -> SimpleNamespace:
            events.append("collect")
            return SimpleNamespace(
                session_id="one", state=SimpleNamespace(value="review"),
                query_text="dentist Vigo", observations=[SimpleNamespace(
                    result_rank=1,
                    business=SimpleNamespace(
                        name="Dentist", category="Dentist", website=None,
                        source_url=None, provider_key="one", country_code="ES",
                        locality="Vigo", administrative_area="Pontevedra",
                    ),
                    first_seen_scroll_step=0,
                )], progress=None,
            )

        def stop(self, _session_id: str) -> None:
            events.append("stop")

    monkeypatch.setattr(acceptance, "SubprocessPlaywrightDiscoveryProvider",
                        lambda **_kw: FakeProvider())
    monkeypatch.setattr(acceptance, "AssistedDiscoveryManager", FakeManager)
    monkeypatch.setattr(
        "veridra.assisted_discovery_acceptance_cli.time.sleep",
        lambda _n: events.append("sleep"),
    )
    assert acceptance.run([
        "--query", "dentist Vigo", "--country-code", "ES",
        "--automatic", "--settle-seconds", "0",
    ]) == 0
    assert events == [
        "sleep", "status", "sleep", "status", "sleep", "status",
        "ready", "collect", "stop",
    ]
    assert "complete it in the visible Chromium window" in capsys.readouterr().out


def test_automatic_login_timeout_stops_without_collecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    events: list[str] = []

    class FakeProvider:
        def maps_results_ready(self) -> bool:
            events.append("status")
            return False

    class FakeManager:
        def __init__(self, _provider: object) -> None:
            pass

        def launch(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(session_id="one")

        def stop(self, _session_id: str) -> None:
            events.append("stop")

    monkeypatch.setattr(acceptance, "SubprocessPlaywrightDiscoveryProvider",
                        lambda **_kw: FakeProvider())
    monkeypatch.setattr(acceptance, "AssistedDiscoveryManager", FakeManager)
    monkeypatch.setattr(
        "veridra.assisted_discovery_acceptance_cli.time.sleep", lambda _n: None
    )
    monotonic_times = iter([0.0, 2.0])
    monkeypatch.setattr(
        "veridra.assisted_discovery_acceptance_cli.time.monotonic",
        lambda: next(monotonic_times),
    )
    assert acceptance.run([
        "--query", "dentist Vigo", "--country-code", "ES",
        "--automatic", "--login-timeout-seconds", "1",
    ]) == 1
    assert events == ["status", "stop"]
