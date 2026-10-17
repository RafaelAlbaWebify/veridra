from __future__ import annotations

from io import StringIO

import pytest

from veridra.assisted_browser_provider import (
    SubprocessPlaywrightDiscoveryProvider,
    VisibleBrowserUnavailable,
)
from veridra.assisted_discovery import (
    AssistedDiscoveryManager,
    AssistedDiscoveryState,
    BoundedDiscoveryLimits,
)


class BrokenProvider:
    def __init__(self) -> None:
        self.stopped = False

    def launch(self, *, start_url: str) -> None:
        pass

    def collect_bounded(self, *, query_text: str, query_sequence: int,
                        limits: BoundedDiscoveryLimits) -> None:
        raise VisibleBrowserUnavailable("Child process exited")

    def stop(self) -> None:
        self.stopped = True


def test_transport_death_marks_manager_failed_and_stops_child() -> None:
    provider = BrokenProvider()
    manager = AssistedDiscoveryManager(provider)
    launched = manager.launch(query_text="plumbers", query_sequence=1,
                              start_url="https://www.google.com/maps")
    manager.mark_ready(launched.session_id or "")
    with pytest.raises(VisibleBrowserUnavailable, match="Child process exited"):
        manager.collect(launched.session_id or "", limits=BoundedDiscoveryLimits())
    assert manager.snapshot().state is AssistedDiscoveryState.failed
    assert manager.snapshot().error == "Child process exited"
    assert provider.stopped


class HungPipe:
    def readline(self) -> str:
        return "never read"


class FakeChild:
    def __init__(self) -> None:
        self.stdin = StringIO()
        self.stdout = HungPipe()
        self.terminated = False

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, *, timeout: int) -> int:
        return 0


def test_timeout_invalidates_child_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SubprocessPlaywrightDiscoveryProvider(country_code="ES")
    child = FakeChild()
    provider._process = child  # type: ignore[assignment]
    def timeout(_stream: object) -> str:
        raise VisibleBrowserUnavailable("The visible browser did not respond in time.")
    monkeypatch.setattr(provider, "_readline_with_timeout", timeout)
    with pytest.raises(VisibleBrowserUnavailable, match="did not respond"):
        provider._request(command="collect_bounded", payload={})
    assert child.terminated
    assert provider._process is None
