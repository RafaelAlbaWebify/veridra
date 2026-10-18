from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from collections.abc import Sequence
from urllib.parse import quote_plus

from .assisted_browser_provider import SubprocessPlaywrightDiscoveryProvider
from .assisted_discovery import AssistedDiscoveryManager, BoundedDiscoveryLimits


def build_start_url(query_text: str) -> str:
    query = query_text.strip()
    if not query:
        raise ValueError("query_text cannot be blank.")
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-assisted-discovery-check")
    parser.add_argument("--query", required=True)
    parser.add_argument("--country-code", required=True)
    parser.add_argument("--locality", default="")
    parser.add_argument("--administrative-area", default="")
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--max-scrolls", type=int, default=5)
    parser.add_argument("--max-seconds", type=float, default=30.0)
    parser.add_argument("--max-stagnant-scrolls", type=int, default=2)
    parser.add_argument("--automatic", action="store_true", help="Run without operator input.")
    parser.add_argument("--settle-seconds", type=float, default=8.0)
    parser.add_argument("--login-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--profile-directory", type=Path, default=Path.home() / ".veridra" / "maps-acceptance-profile")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.settle_seconds < 0 or args.settle_seconds > 30:
        raise ValueError("settle-seconds must be between 0 and 30.")
    if args.login_timeout_seconds < 1 or args.login_timeout_seconds > 900:
        raise ValueError("login-timeout-seconds must be between 1 and 900.")
    limits = BoundedDiscoveryLimits(
        max_results=args.max_results,
        max_scrolls=args.max_scrolls,
        max_elapsed_seconds=args.max_seconds,
        max_stagnant_scrolls=args.max_stagnant_scrolls,
    )
    provider = SubprocessPlaywrightDiscoveryProvider(
        country_code=args.country_code,
        locality=args.locality,
        administrative_area=args.administrative_area,
        profile_directory=args.profile_directory,
    )
    manager = AssistedDiscoveryManager(provider)
    query = args.query.strip()
    session = manager.launch(
        query_text=query,
        query_sequence=1,
        start_url=build_start_url(query),
    )
    try:
        if args.automatic:
            time.sleep(args.settle_seconds)
            deadline = time.monotonic() + args.login_timeout_seconds
            notified = False
            while not provider.maps_results_ready():
                if not notified:
                    print(
                        "Waiting for Google Maps results. If Google shows sign-in "
                        "or consent, complete it in the visible Chromium window. "
                        "The browser will stay open while waiting.",
                        flush=True,
                    )
                    notified = True
                if time.monotonic() >= deadline:
                    print("FAIL: Google Maps results did not become ready.", flush=True)
                    return 1
                time.sleep(2)
        else:
            input(
                "Visible Chromium opened. Confirm the Google Maps results panel is visible, "
                "then press Enter to collect the bounded sample..."
            )
        session = manager.mark_ready(session.session_id or "")
        session = manager.collect(session.session_id or "", limits=limits)
        payload: dict[str, object] = {
            "session_id": session.session_id,
            "state": session.state.value,
            "query_text": session.query_text,
            "progress": (
                {
                    "unique_results": session.progress.unique_results,
                    "scroll_step": session.progress.scroll_step,
                    "elapsed_seconds": round(session.progress.elapsed_seconds, 3),
                    "stop_reason": (
                        session.progress.stop_reason.value
                        if session.progress.stop_reason is not None
                        else None
                    ),
                }
                if session.progress is not None
                else None
            ),
            "observations": [
                {
                    "rank": item.result_rank,
                    "name": item.business.name,
                    "category": item.business.category,
                    "website": (
                        str(item.business.website) if item.business.website is not None else None
                    ),
                    "source_url": (
                        str(item.business.source_url)
                        if item.business.source_url is not None
                        else None
                    ),
                    "provider_key": item.business.provider_key,
                    "country_code": item.business.country_code,
                    "locality": item.business.locality,
                    "administrative_area": item.business.administrative_area,
                    "first_seen_scroll_step": item.first_seen_scroll_step,
                }
                for item in session.observations
            ],
            "persistence": "none",
        }
        if args.automatic:
            payload["acceptance_passed"] = len(session.observations) > 0
            payload["mode"] = "automatic_live"
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if not args.automatic or session.observations else 1
    finally:
        manager.stop(session.session_id)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
