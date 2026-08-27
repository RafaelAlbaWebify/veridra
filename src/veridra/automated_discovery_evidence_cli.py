from __future__ import annotations

import argparse
import io
import json
import time
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .agency_prospect_discovery_evidence_web import (
    _csv_bytes,
    _json_bytes,
    _safe_filename,
    _summary_markdown,
)
from .agency_prospect_discovery_web import _prospect_for_ingest
from .assisted_browser_provider import (
    SubprocessPlaywrightDiscoveryProvider,
    VisibleBrowserUnavailable,
)
from .assisted_discovery import BoundedDiscoveryLimits, TraversalResult
from .assisted_discovery_acceptance_cli import build_start_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-discovery-evidence")
    parser.add_argument("--query", default="dentist in Dublin, IE")
    parser.add_argument("--country-code", default="IE")
    parser.add_argument("--locality", default="Dublin")
    parser.add_argument("--administrative-area", default="Dublin")
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--max-scrolls", type=int, default=10)
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--max-stagnant-scrolls", type=int, default=3)
    parser.add_argument("--startup-wait-seconds", type=float, default=4.0)
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    return parser


def _observations(result: TraversalResult) -> list[dict[str, object]]:
    return [
        {
            "query_text": item.query_text,
            "query_sequence": item.query_sequence,
            "result_rank": item.result_rank,
            "first_seen_scroll_step": item.first_seen_scroll_step,
            "business": item.business.model_dump(mode="json"),
        }
        for item in result.observations
    ]


def _build_archive(*, result: TraversalResult, query_text: str, generated_at: str) -> bytes:
    observations = _observations(result)
    ingest_preview = [
        {
            "result_rank": item.result_rank,
            "prospect": _prospect_for_ingest(item).model_dump(mode="json"),
        }
        for item in result.observations
    ]
    progress = result.progress
    website_count = sum(
        1
        for row in observations
        if isinstance(row["business"], dict) and row["business"].get("website")
    )
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "query_text": query_text,
        "query_sequence": progress.query_sequence,
        "state": "review",
        "captured_count": len(observations),
        "website_captured_count": website_count,
        "no_website_captured_count": len(observations) - website_count,
        "ingest_preview_count": len(ingest_preview),
        "progress": {
            "scroll_step": progress.scroll_step,
            "unique_results": progress.unique_results,
            "stagnant_scrolls": progress.stagnant_scrolls,
            "elapsed_seconds": progress.elapsed_seconds,
            "stop_reason": progress.stop_reason.value if progress.stop_reason else None,
        },
        "persistence": "none",
        "execution": "automated-local-backend",
    }

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("captured_observations.json", _json_bytes(observations))
        archive.writestr("captured_businesses.csv", _csv_bytes(observations))
        archive.writestr("ingest_preview.json", _json_bytes(ingest_preview))
        archive.writestr(
            "README.md",
            _summary_markdown(
                session_id="automated-local-backend",
                query_text=query_text,
                observations=observations,
                generated_at=generated_at,
            ).encode("utf-8"),
        )
    return archive_buffer.getvalue()


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.startup_wait_seconds < 0 or args.startup_wait_seconds > 60:
        raise ValueError("startup-wait-seconds must be between 0 and 60.")

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
    query = args.query.strip()
    if not query:
        raise ValueError("query cannot be blank.")

    print(f"[Veridra] Opening Google Maps for: {query}")
    provider.launch(start_url=build_start_url(query))
    try:
        if args.startup_wait_seconds:
            time.sleep(args.startup_wait_seconds)
        print("[Veridra] Collecting bounded discovery evidence automatically...")
        try:
            result = provider.collect_bounded(
                query_text=query,
                query_sequence=1,
                limits=limits,
            )
        except VisibleBrowserUnavailable as exc:
            print(f"[Veridra] Collection failed: {exc}")
            print(
                "[Veridra] If Google requires consent, sign-in, or CAPTCHA, complete it in the "
                "persistent browser profile and rerun this command."
            )
            return 2

        generated_at = datetime.now(UTC).isoformat()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output_directory.mkdir(parents=True, exist_ok=True)
        filename = f"VERIDRA_DISCOVERY_{_safe_filename(query)}_{stamp}.zip"
        output_path = args.output_directory / filename
        output_path.write_bytes(
            _build_archive(result=result, query_text=query, generated_at=generated_at)
        )
        stop_reason = result.progress.stop_reason
        summary = {
            "output": str(output_path),
            "captured": len(result.observations),
            "websites": sum(1 for item in result.observations if item.business.website is not None),
            "no_websites": sum(
                1 for item in result.observations if item.business.website is None
            ),
            "stop_reason": stop_reason.value if stop_reason is not None else None,
            "persistence": "none",
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    finally:
        provider.stop()


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
