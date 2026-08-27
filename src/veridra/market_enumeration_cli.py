from __future__ import annotations

import argparse
import json
import time
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .assisted_browser_provider import (
    SubprocessPlaywrightDiscoveryProvider,
    VisibleBrowserUnavailable,
)
from .assisted_discovery import BoundedDiscoveryLimits, TraversalResult
from .assisted_discovery_acceptance_cli import build_start_url
from .market_enumeration import aggregate_market, dublin_dentist_queries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-market-enumeration")
    parser.add_argument(
        "--plan",
        choices=("dublin-dentists",),
        default="dublin-dentists",
    )
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--country-code", default="IE")
    parser.add_argument("--locality", default="Dublin")
    parser.add_argument("--administrative-area", default="Dublin")
    parser.add_argument("--max-results-per-query", type=int, default=50)
    parser.add_argument("--max-scrolls-per-query", type=int, default=20)
    parser.add_argument("--max-seconds-per-query", type=float, default=120.0)
    parser.add_argument("--max-stagnant-scrolls", type=int, default=3)
    parser.add_argument("--startup-wait-seconds", type=float, default=4.0)
    parser.add_argument("--between-query-wait-seconds", type=float, default=1.0)
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    return parser


def _queries(args: argparse.Namespace) -> tuple[str, ...]:
    explicit = tuple(query.strip() for query in args.query if query.strip())
    if explicit:
        return explicit
    if args.plan == "dublin-dentists":
        return dublin_dentist_queries()
    raise ValueError("No market-enumeration query plan is available.")


def _business_payload(item: object) -> dict[str, object]:
    market_business = item
    business = market_business.business
    return {
        "business": business.model_dump(mode="json"),
        "first_query_text": market_business.first_query_text,
        "first_query_sequence": market_business.first_query_sequence,
        "first_result_rank": market_business.first_result_rank,
        "seen_in_queries": list(market_business.seen_in_queries),
        "observation_count": market_business.observation_count,
    }


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.startup_wait_seconds < 0 or args.startup_wait_seconds > 60:
        raise ValueError("startup-wait-seconds must be between 0 and 60.")
    if args.between_query_wait_seconds < 0 or args.between_query_wait_seconds > 60:
        raise ValueError("between-query-wait-seconds must be between 0 and 60.")

    queries = _queries(args)
    if not queries:
        raise ValueError("At least one query is required.")

    limits = BoundedDiscoveryLimits(
        max_results=args.max_results_per_query,
        max_scrolls=args.max_scrolls_per_query,
        max_elapsed_seconds=args.max_seconds_per_query,
        max_stagnant_scrolls=args.max_stagnant_scrolls,
    )

    results: list[TraversalResult] = []
    for sequence, query in enumerate(queries, start=1):
        provider = SubprocessPlaywrightDiscoveryProvider(
            country_code=args.country_code,
            locality=args.locality,
            administrative_area=args.administrative_area,
        )
        print(f"[Veridra] [{sequence}/{len(queries)}] Opening Google Maps for: {query}")
        provider.launch(start_url=build_start_url(query))
        try:
            if args.startup_wait_seconds:
                time.sleep(args.startup_wait_seconds)
            print("[Veridra] Collecting bounded market-enumeration evidence...")
            try:
                result = provider.collect_bounded(
                    query_text=query,
                    query_sequence=sequence,
                    limits=limits,
                )
            except VisibleBrowserUnavailable as exc:
                print(f"[Veridra] Collection failed for query {sequence}: {exc}")
                print(
                    "[Veridra] Complete any ordinary Google consent/sign-in/CAPTCHA in the "
                    "persistent browser profile and rerun the market enumeration."
                )
                return 2
            results.append(result)
            reason = result.progress.stop_reason
            print(
                json.dumps(
                    {
                        "query_sequence": sequence,
                        "query": query,
                        "captured": len(result.observations),
                        "stop_reason": reason.value if reason is not None else None,
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            provider.stop()
        if args.between_query_wait_seconds and sequence < len(queries):
            time.sleep(args.between_query_wait_seconds)

    enumeration = aggregate_market(results)
    generated_at = datetime.now(UTC).isoformat()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output = args.output_directory / f"VERIDRA_MARKET_ENUMERATION_{stamp}.zip"

    businesses = [_business_payload(item) for item in enumeration.businesses]
    coverage = [
        {
            "query_text": item.query_text,
            "query_sequence": item.query_sequence,
            "captured": item.captured,
            "new_unique": item.new_unique,
            "duplicate_observations": item.duplicate_observations,
            "stop_reason": item.stop_reason,
        }
        for item in enumeration.coverage
    ]
    website_count = sum(
        1 for item in enumeration.businesses if item.business.website is not None
    )
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "plan": args.plan,
        "query_count": len(queries),
        "raw_observation_count": enumeration.raw_observation_count,
        "unique_business_count": len(enumeration.businesses),
        "website_observed_count": website_count,
        "no_website_observed_count": len(enumeration.businesses) - website_count,
        "dedupe_identity": "provider + provider_key; Google Maps provider key is based on canonical place identity where available",
        "selection_rule": "No opportunity ranking is applied during enumeration; Google result rank is retained only as provenance.",
        "coverage_rule": "Every configured query is executed unless collection fails; low marginal yield does not stop later queries.",
        "persistence": "none",
        "outreach": "none",
    }

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr(
            "market_businesses.json",
            json.dumps(businesses, indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "query_coverage.json",
            json.dumps(coverage, indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "README.md",
            "# VERIDRA Market Enumeration Evidence\n\n"
            "This pack aggregates multiple bounded Google Maps result sets into one deduplicated "
            "local-market candidate set. Google result rank is provenance only and is not used as "
            "VERIDRA's opportunity ranking. Every configured query is attempted independently. "
            "No prospect state is mutated and no outreach is sent.\n",
        )

    print(
        json.dumps(
            {
                "output": str(output),
                "queries_run": len(queries),
                "raw_observations": enumeration.raw_observation_count,
                "unique_businesses": len(enumeration.businesses),
                "websites_observed": website_count,
                "no_websites_observed": len(enumeration.businesses) - website_count,
                "persistence": "none",
                "outreach": "none",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
