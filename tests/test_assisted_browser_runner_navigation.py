from __future__ import annotations

import io
import sys
from pathlib import Path
from types import ModuleType

import pytest

from veridra import assisted_browser_runner as runner
from veridra.assisted_browser_protocol import decode_response
from veridra.assisted_browser_runner import run


def test_failed_initial_maps_navigation_does_not_abort_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class FakePage:
        def goto(self, *_args: object, **_kwargs: object) -> None:
            events.append("goto")
            assert output.getvalue(), "The startup acknowledgement must precede Maps navigation."
            raise RuntimeError("navigation aborted")

    page = FakePage()

    class FakeContext:
        pages = [page]

        def close(self) -> None:
            events.append("close")

    context = FakeContext()

    class FakeChromium:
        def launch_persistent_context(
            self, *_args: object, **_kwargs: object
        ) -> FakeContext:
            events.append("launch")
            return context

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self) -> FakePlaywright:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

    module = ModuleType("playwright.sync_api")
    module.__dict__["sync_playwright"] = lambda: FakePlaywright()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert run([
        "--profile-directory", str(tmp_path),
        "--start-url", "https://www.google.com/maps",
    ]) == 0
    assert events == ["launch", "goto", "close"]
    assert decode_response(output.getvalue(), expected_request_id="startup").ok is True


def test_gui_collect_waits_for_maps_results_after_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Page:
        def __init__(self, ready: bool) -> None:
            self.ready = ready

    login = Page(False)
    maps = Page(True)

    class Context:
        pages = [login]

    context = Context()
    ticks = iter([0.0, 0.1, 0.2])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))

    def sleep(_seconds: float) -> None:
        context.pages.append(maps)

    monkeypatch.setattr(runner.time, "sleep", sleep)
    monkeypatch.setattr(runner, "maps_results_visible", lambda page: page.ready)
    assert runner._await_maps_results(context, timeout_seconds=1.0) is maps


def test_gui_collect_rejects_non_maps_after_bounded_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veridra.assisted_google_maps import VisiblePageUnsupported

    class Context:
        pages = [object()]

    ticks = iter([0.0, 61.0])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "maps_results_visible", lambda _page: False)
    with pytest.raises(VisiblePageUnsupported, match="within 60 seconds"):
        runner._await_maps_results(Context())
