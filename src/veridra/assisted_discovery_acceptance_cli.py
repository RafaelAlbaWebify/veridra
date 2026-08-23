from __future__ import annotations

import argparse
import json
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
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
    )
    manager = AssistedDiscoveryManager(provider)
    query = args.query.strip()
    session = manager.launch(
        query_text=query,
        query_sequence=1,
        start_url=build_start_url(query),
    )
    try:
        input(
            "Visible Chromium opened. Confirm the Google Maps results panel is visible, "
            "then press Enter to collect the bounded sample..."
        )
        session = manager.mark_ready(session.session_id or "")
        session = manager.collect(session.session_id or "", limits=limits)
        payload = {
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
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    finally:
        manager.stop(session.session_id)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
