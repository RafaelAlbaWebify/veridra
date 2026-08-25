from __future__ import annotations

import argparse
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from .assisted_browser_protocol import (
    BrowserProtocolError,
    ProtocolResponse,
    decode_request,
    encode_response,
    write_message,
)
from .assisted_discovery import BoundedDiscoveryLimits
from .assisted_google_maps import (
    VisiblePageSelectorDrift,
    VisiblePageUnsupported,
    traverse_google_maps_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-assisted-browser")
    parser.add_argument("--profile-directory", type=Path, required=True)
    parser.add_argument("--start-url", required=True)
    return parser


def _respond(response: ProtocolResponse) -> None:
    write_message(sys.stdout, encode_response(response))


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BrowserProtocolError(f"{key} must be an integer.")
    return value


def _required_float(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise BrowserProtocolError(f"{key} must be numeric.")
    return float(value)


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BrowserProtocolError(f"{key} must be a non-empty string.")
    return value.strip()


def _optional_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str):
        raise BrowserProtocolError(f"{key} must be a string.")
    return value.strip()


def _handle_collect_bounded(page: object, payload: dict[str, object]) -> dict[str, object]:
    query_text = _required_text(payload, "query_text")
    query_sequence = _required_int(payload, "query_sequence")
    country_code = _required_text(payload, "country_code")
    limits = BoundedDiscoveryLimits(
        max_results=_required_int(payload, "max_results"),
        max_scrolls=_required_int(payload, "max_scrolls"),
        max_elapsed_seconds=_required_float(payload, "max_elapsed_seconds"),
        max_stagnant_scrolls=_required_int(payload, "max_stagnant_scrolls"),
    )
    result = traverse_google_maps_results(
        page,
        query_text=query_text,
        query_sequence=query_sequence,
        limits=limits,
        country_code=country_code,
        locality=_optional_text(payload, "locality"),
        administrative_area=_optional_text(payload, "administrative_area"),
    )
    stop_reason = result.progress.stop_reason
    return {
        "businesses": [
            observation.business.model_dump(mode="json") for observation in result.observations
        ],
        "observations": [
            {
                "query_text": observation.query_text,
                "query_sequence": observation.query_sequence,
                "result_rank": observation.result_rank,
                "first_seen_scroll_step": observation.first_seen_scroll_step,
            }
            for observation in result.observations
        ],
        "progress": {
            "query_text": result.progress.query_text,
            "query_sequence": result.progress.query_sequence,
            "scroll_step": result.progress.scroll_step,
            "unique_results": result.progress.unique_results,
            "stagnant_scrolls": result.progress.stagnant_scrolls,
            "elapsed_seconds": result.progress.elapsed_seconds,
            "stop_reason": stop_reason.value if stop_reason is not None else None,
        },
    }


def _safe_browser_error(exc: Exception) -> str:
    detail = " ".join(str(exc).split())[:300]
    error_type = type(exc).__name__
    if detail:
        return f"The visible browser could not collect the current results ({error_type}: {detail})."
    return f"The visible browser could not collect the current results ({error_type})."


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for assisted discovery.") from exc

    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(args.profile_directory),
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(str(args.start_url))
        while not stopping and context.pages:
            line = sys.stdin.readline()
            if line == "":
                break
            request_id = "unknown"
            try:
                request = decode_request(line)
                request_id = request.request_id
                if request.command != "collect_bounded":
                    _respond(
                        ProtocolResponse(
                            request_id=request.request_id,
                            ok=False,
                            error_code="unsupported_command",
                            error_message="The browser command is not supported.",
                        )
                    )
                    continue
                result = _handle_collect_bounded(page, request.payload)
                _respond(
                    ProtocolResponse(
                        request_id=request.request_id,
                        ok=True,
                        result=result,
                    )
                )
            except VisiblePageUnsupported as exc:
                _respond(
                    ProtocolResponse(
                        request_id=request_id,
                        ok=False,
                        error_code="unsupported_page",
                        error_message=str(exc),
                    )
                )
            except VisiblePageSelectorDrift as exc:
                _respond(
                    ProtocolResponse(
                        request_id=request_id,
                        ok=False,
                        error_code="selector_drift",
                        error_message=str(exc),
                    )
                )
            except (BrowserProtocolError, ValueError) as exc:
                _respond(
                    ProtocolResponse(
                        request_id=request_id,
                        ok=False,
                        error_code="invalid_request",
                        error_message=str(exc),
                    )
                )
            except Exception as exc:
                _respond(
                    ProtocolResponse(
                        request_id=request_id,
                        ok=False,
                        error_code="browser_error",
                        error_message=_safe_browser_error(exc),
                    )
                )
        context.close()
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
