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
from .market_enumeration import MarketBusiness, aggregate_market, dublin_dentist_queries


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


def _business_payload(item: MarketBusiness) -> dict[str, object]:
    return {
        "business": item.business.model_dump(mode="json"),
        "first_query_text": item.first_query_text,
        "first_query_sequence": item.first_query_sequence,
        "first_result_rank": item.first_result_rank,
        "seen_in_queries": list(item.seen_in_queries),
        "observation_count": item.observation_count,
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
    failures: dict[int, str] = {}
    for sequence, query in enumerate(queries, start=1):
        provider = SubprocessPlaywrightDiscoveryProvider(
            country_code=args.country_code,
            locality=args.locality,
            administrative_area=args.administrative_area,
        )
        print(f"[Veridra] [{sequence}/{len(queries)}] Opening Google Maps for: {query}")
        try:
            provider.launch(start_url=build_start_url(query))
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
                failures[sequence] = str(exc)
                print(f"[Veridra] Query {sequence} unavailable; recording failure and continuing.")
                print(f"[Veridra] Reason: {exc}")
                continue
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
        except Exception as exc:
            failures[sequence] = str(exc)
            print(f"[Veridra] Query {sequence} failed; recording failure and continuing.")
            print(f"[Veridra] Reason: {exc}")
        finally:
            provider.stop()
        if args.between_query_wait_seconds and sequence < len(queries):
            time.sleep(args.between_query_wait_seconds)

    if not results:
        raise RuntimeError("All market-enumeration queries failed; no evidence was collected.")

    enumeration = aggregate_market(results)
    generated_at = datetime.now(UTC).isoformat()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output = args.output_directory / f"VERIDRA_MARKET_ENUMERATION_{stamp}.zip"

    businesses = [_business_payload(item) for item in enumeration.businesses]
    successful_coverage = {item.query_sequence: item for item in enumeration.coverage}
    coverage: list[dict[str, object]] = []
    for sequence, query in enumerate(queries, start=1):
        successful = successful_coverage.get(sequence)
        if successful is not None:
            coverage.append(
                {
                    "query_text": successful.query_text,
                    "query_sequence": successful.query_sequence,
                    "captured": successful.captured,
                    "new_unique": successful.new_unique,
                    "duplicate_observations": successful.duplicate_observations,
                    "stop_reason": successful.stop_reason,
                    "collection_status": "ok",
                    "error": None,
                }
            )
            continue
        coverage.append(
            {
                "query_text": query,
                "query_sequence": sequence,
                "captured": 0,
                "new_unique": 0,
                "duplicate_observations": 0,
                "stop_reason": "provider_error",
                "collection_status": "failed",
                "error": failures.get(sequence, "Unknown query collection failure."),
            }
        )

    website_count = sum(
        1 for item in enumeration.businesses if item.business.website is not None
    )
    failed_count = len(failures)
    manifest = {
        "schema_version": 2,
        "generated_at": generated_at,
        "plan": args.plan,
        "query_count": len(queries),
        "queries_succeeded": len(queries) - failed_count,
        "queries_failed": failed_count,
        "raw_observation_count": enumeration.raw_observation_count,
        "unique_business_count": len(enumeration.businesses),
        "website_observed_count": website_count,
        "no_website_observed_count": len(enumeration.businesses) - website_count,
        "dedupe_identity": (
            "provider + provider_key; Google Maps provider key is based on canonical "
            "place identity where available"
        ),
        "selection_rule": (
            "No opportunity ranking is applied during enumeration; Google result rank is "
            "retained only as provenance."
        ),
        "coverage_rule": (
            "Every configured query is attempted independently. Individual query collection "
            "failures are preserved in coverage evidence and do not discard successful queries."
        ),
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
            "A failed query is recorded in coverage evidence without discarding successful query "
            "results. No prospect state is mutated and no outreach is sent.\n",
        )

    print(
        json.dumps(
            {
                "output": str(output),
                "queries_planned": len(queries),
                "queries_succeeded": len(queries) - failed_count,
                "queries_failed": failed_count,
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
