from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from veridra.assisted_browser_protocol import ProtocolResponse, encode_response
from veridra.assisted_browser_provider import (
    SubprocessPlaywrightDiscoveryProvider,
    VisibleBrowserUnavailable,
)


class _Process:
    def __init__(self, message: str) -> None:
        self.stdin = StringIO()
        self.stdout = StringIO(message)
        self.terminated = False

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, *, timeout: int) -> int:
        return 0


def test_launch_requires_child_ready_ack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process = _Process(encode_response(ProtocolResponse(
        request_id="startup", ok=True, result={"ready": True},
    )))
    monkeypatch.setattr(
        "veridra.assisted_browser_provider.subprocess.Popen",
        lambda *_a, **_k: process,
    )
    provider = SubprocessPlaywrightDiscoveryProvider(country_code="ES", profile_directory=tmp_path)
    provider.launch(start_url="https://www.google.com/maps")
    assert not process.terminated


def test_launch_rejects_child_exit_before_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    process = _Process("")
    monkeypatch.setattr(
        "veridra.assisted_browser_provider.subprocess.Popen",
        lambda *_a, **_k: process,
    )
    provider = SubprocessPlaywrightDiscoveryProvider(country_code="ES", profile_directory=tmp_path)
    with pytest.raises(VisibleBrowserUnavailable, match="exited before collection"):
        provider.launch(start_url="https://www.google.com/maps")
    assert process.terminated
