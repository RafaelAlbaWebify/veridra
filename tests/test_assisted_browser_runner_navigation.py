from __future__ import annotations

import io
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from veridra.assisted_browser_runner import run


def test_failed_initial_maps_navigation_does_not_abort_browser(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class FakePage:
        def goto(self, *_args: object, **_kwargs: object) -> None:
            events.append("goto")
            raise RuntimeError("navigation aborted")

    page = FakePage()

    class FakeContext:
        pages = [page]

        def close(self) -> None:
            events.append("close")

    context = FakeContext()

    class FakeChromium:
        def launch_persistent_context(self, *_args: object, **_kwargs: object) -> FakeContext:
            events.append("launch")
            return context

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self) -> FakePlaywright:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

    module = ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: FakePlaywright()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert run(["--profile-directory", str(tmp_path), "--start-url", "https://www.google.com/maps"]) == 0
    assert events == ["launch", "goto", "close"]
