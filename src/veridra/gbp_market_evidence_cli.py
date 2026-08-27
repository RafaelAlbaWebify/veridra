from __future__ import annotations

import argparse
import json
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .gbp_profile_evidence_cli import _capture, _failed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-gbp-market-evidence")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument(
        "--profile-directory",
        type=Path,
        default=Path.home() / ".veridra" / "browser-profile",
    )
    parser.add_argument("--max-businesses", type=int, default=500)
    parser.add_argument("--headless", action="store_true")
    return parser


def _latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _load_market_contexts(path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("market_businesses.json"))
    if not isinstance(raw, list):
        raise ValueError("market_businesses.json must contain a list.")

    contexts: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        business = item.get("business")
        if not isinstance(business, dict):
            continue
        name = _text(business.get("name"))
        source_url = _text(business.get("source_url"))
        if not name or not source_url:
            continue
        seen_in_queries = item.get("seen_in_queries")
        queries = [query for query in seen_in_queries if isinstance(query, str)] if isinstance(seen_in_queries, list) else []
        contexts.append(
            {
                "business_name": name,
                "source_url": source_url,
                "website": _text(business.get("website")) or None,
                "category": _text(business.get("category")),
                "signals": {
                    "rating": _number(business.get("rating")),
                    "review_count": _integer(business.get("review_count")),
                },
                "provider_key": _text(business.get("provider_key")),
                "first_query_text": item.get("first_query_text"),
                "first_query_sequence": item.get("first_query_sequence"),
                "first_result_rank": item.get("first_result_rank"),
                "seen_in_queries": queries,
                "observation_count": item.get("observation_count"),
            }
        )
    return contexts


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_businesses < 1 or args.max_businesses > 500:
        raise ValueError("max-businesses must be between 1 and 500.")

    input_path = args.input or _latest(args.downloads, "VERIDRA_MARKET_ENUMERATION_*.zip")
    if input_path is None or not input_path.is_file():
        raise FileNotFoundError("No VERIDRA market-enumeration ZIP was found.")

    contexts = _load_market_contexts(input_path)[: args.max_businesses]
    if not contexts:
        raise ValueError("The market-enumeration ZIP contains no eligible Google Maps source URLs.")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for GBP evidence collection.") from exc

    args.profile_directory.mkdir(parents=True, exist_ok=True)
    collected: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            str(args.profile_directory),
            headless=args.headless,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        for index, context in enumerate(contexts, start=1):
            name = _text(context.get("business_name"))
            print(f"[Veridra] GBP market enrichment [{index}/{len(contexts)}]: {name}")
            try:
                evidence = _capture(page, context)
                payload = evidence.model_dump(mode="json")
            except Exception as exc:
                payload = _failed(context, exc)
            payload["provider_key"] = context.get("provider_key")
            payload["first_query_text"] = context.get("first_query_text")
            payload["first_query_sequence"] = context.get("first_query_sequence")
            payload["first_result_rank"] = context.get("first_result_rank")
            payload["seen_in_queries"] = context.get("seen_in_queries")
            payload["observation_count"] = context.get("observation_count")
            collected.append(payload)
        browser.close()

    ok_count = sum(1 for row in collected if row.get("collection_status") == "ok")
    without_website_before = sum(1 for context in contexts if not context.get("website"))
    without_website_after = sum(
        1
        for row in collected
        if row.get("collection_status") == "ok" and not row.get("website_url")
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output = args.output_directory / f"VERIDRA_GBP_MARKET_EVIDENCE_{stamp}.zip"
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_market_enumeration": input_path.name,
        "businesses_requested": len(contexts),
        "businesses_collected": ok_count,
        "businesses_failed": len(contexts) - ok_count,
        "no_website_observed_before_gbp": without_website_before,
        "no_website_observed_after_gbp": without_website_after,
        "method": (
            "deduplicated market enumeration followed by visible public Google Maps detail-page "
            "observation for every eligible business"
        ),
        "selection_rule": "No opportunity ranking is applied before GBP enrichment.",
        "absence_rule": (
            "An unobserved field is a collection result, not proof that the business owner "
            "failed to configure the Google Business Profile field."
        ),
        "persistence": "none",
        "outreach": "none",
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr(
            "gbp_market_evidence.json",
            json.dumps(collected, indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "README.md",
            "# VERIDRA GBP Market Evidence\n\n"
            "Read-only GBP enrichment of the deduplicated local-market enumeration. Every eligible "
            "market business is enriched before opportunity ranking. Market query provenance is "
            "preserved alongside public GBP evidence. No prospect state is mutated and no outreach "
            "is sent.\n",
        )

    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output),
                "businesses_requested": len(contexts),
                "businesses_collected": ok_count,
                "businesses_failed": len(contexts) - ok_count,
                "no_website_observed_before_gbp": without_website_before,
                "no_website_observed_after_gbp": without_website_after,
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
