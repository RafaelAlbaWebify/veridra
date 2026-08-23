from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from .assisted_browser_protocol import (
    BrowserProtocolError,
    ProtocolRequest,
    decode_response,
    encode_request,
    write_message,
)
from .assisted_discovery import (
    AssistedDiscoveryConflict,
    BoundedDiscoveryLimits,
    TraversalObservation,
    TraversalProgress,
    TraversalResult,
    TraversalStopReason,
)
from .prospect_discovery import ObservedBusiness


class VisibleBrowserUnavailable(RuntimeError):
    pass


class SubprocessPlaywrightDiscoveryProvider:
    """Run visible-browser discovery in a local child process over stdin/stdout only."""

    def __init__(
        self,
        *,
        country_code: str,
        locality: str = "",
        administrative_area: str = "",
        profile_directory: Path | None = None,
        response_timeout_seconds: float = 120.0,
    ) -> None:
        clean_country = country_code.strip().upper()
        if len(clean_country) != 2:
            raise ValueError("country_code must contain exactly two characters.")
        if response_timeout_seconds <= 0 or response_timeout_seconds > 600:
            raise ValueError("response_timeout_seconds must be between 0 and 600.")
        configured_profile = os.environ.get("VERIDRA_BROWSER_PROFILE_DIRECTORY", "").strip()
        default_profile = Path.home() / ".veridra" / "browser-profile"
        self._profile_directory = profile_directory or (
            Path(configured_profile) if configured_profile else default_profile
        )
        self._country_code = clean_country
        self._locality = locality.strip()
        self._administrative_area = administrative_area.strip()
        self._response_timeout_seconds = response_timeout_seconds
        self._process: subprocess.Popen[str] | None = None

    def launch(self, *, start_url: str) -> None:
        if self._process is not None and self._process.poll() is None:
            raise AssistedDiscoveryConflict("A visible browser process is already active.")
        self._profile_directory.mkdir(parents=True, exist_ok=True)
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "veridra.assisted_browser_runner",
                "--profile-directory",
                str(self._profile_directory),
                "--start-url",
                start_url,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        if self._process.poll() is not None:
            raise VisibleBrowserUnavailable("The visible browser process exited during launch.")

    def collect_bounded(
        self,
        *,
        query_text: str,
        query_sequence: int,
        limits: BoundedDiscoveryLimits,
    ) -> TraversalResult:
        result = self._request(
            command="collect_bounded",
            payload={
                "query_text": query_text,
                "query_sequence": query_sequence,
                "country_code": self._country_code,
                "locality": self._locality,
                "administrative_area": self._administrative_area,
                "max_results": limits.max_results,
                "max_scrolls": limits.max_scrolls,
                "max_elapsed_seconds": limits.max_elapsed_seconds,
                "max_stagnant_scrolls": limits.max_stagnant_scrolls,
            },
        )
        return self._decode_result(result, limits=limits)

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _request(self, *, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        process = self._require_running_process()
        if process.stdin is None or process.stdout is None:
            raise VisibleBrowserUnavailable(
                "The visible browser communication channel is unavailable."
            )
        request_id = str(uuid4())
        write_message(
            process.stdin,
            encode_request(
                ProtocolRequest(
                    request_id=request_id,
                    command=command,
                    payload=payload,
                )
            ),
        )
        line = self._readline_with_timeout(process.stdout)
        response = decode_response(line, expected_request_id=request_id)
        if not response.ok:
            raise VisibleBrowserUnavailable(
                response.error_message or "The visible-browser operation failed."
            )
        if response.result is None:
            raise BrowserProtocolError("Browser protocol result is missing.")
        return response.result

    def _decode_result(
        self,
        raw: dict[str, Any],
        *,
        limits: BoundedDiscoveryLimits,
    ) -> TraversalResult:
        raw_businesses = raw.get("businesses")
        raw_observations = raw.get("observations")
        raw_progress = raw.get("progress")
        if not isinstance(raw_businesses, list) or not isinstance(raw_observations, list):
            raise BrowserProtocolError("Browser protocol observations are invalid.")
        if len(raw_businesses) != len(raw_observations):
            raise BrowserProtocolError("Browser protocol observation counts do not match.")
        if len(raw_businesses) > limits.max_results:
            raise BrowserProtocolError("Browser process exceeded the configured result limit.")
        if not isinstance(raw_progress, dict):
            raise BrowserProtocolError("Browser protocol progress must be an object.")

        try:
            businesses = [ObservedBusiness.model_validate(item) for item in raw_businesses]
            stop_reason = TraversalStopReason(str(raw_progress["stop_reason"]))
            progress = TraversalProgress(
                query_text=str(raw_progress["query_text"]),
                query_sequence=int(raw_progress["query_sequence"]),
                scroll_step=int(raw_progress["scroll_step"]),
                unique_results=int(raw_progress["unique_results"]),
                stagnant_scrolls=int(raw_progress["stagnant_scrolls"]),
                elapsed_seconds=float(raw_progress["elapsed_seconds"]),
                stop_reason=stop_reason,
            )
            observations = tuple(
                TraversalObservation(
                    business=business,
                    query_text=str(metadata["query_text"]),
                    query_sequence=int(metadata["query_sequence"]),
                    result_rank=int(metadata["result_rank"]),
                    first_seen_scroll_step=int(metadata["first_seen_scroll_step"]),
                )
                for business, metadata in zip(
                    businesses,
                    raw_observations,
                    strict=True,
                )
                if isinstance(metadata, dict)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BrowserProtocolError("Browser protocol discovery result is invalid.") from exc
        if len(observations) != len(businesses):
            raise BrowserProtocolError("Browser protocol observation metadata is invalid.")
        return TraversalResult(observations=observations, progress=progress)

    def _require_running_process(self) -> subprocess.Popen[str]:
        process = self._process
        if process is None or process.poll() is not None:
            raise VisibleBrowserUnavailable("The visible browser process is not running.")
        return process

    def _readline_with_timeout(self, stream: Any) -> str:
        responses: queue.Queue[str | BaseException] = queue.Queue(maxsize=1)

        def read() -> None:
            try:
                responses.put(stream.readline())
            except BaseException as exc:  # pragma: no cover - defensive pipe boundary
                responses.put(exc)

        threading.Thread(target=read, daemon=True).start()
        try:
            value = responses.get(timeout=self._response_timeout_seconds)
        except queue.Empty as exc:
            raise VisibleBrowserUnavailable(
                "The visible browser did not respond in time."
            ) from exc
        if isinstance(value, BaseException):
            raise VisibleBrowserUnavailable(
                "The visible browser response could not be read."
            ) from value
        if value == "":
            raise VisibleBrowserUnavailable(
                "The visible browser process exited before collection completed."
            )
        return value
