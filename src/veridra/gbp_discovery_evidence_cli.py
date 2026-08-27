from __future__ import annotations

import argparse
import json
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .gbp_profile_evidence_cli import _capture, _failed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-gbp-discovery-evidence")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument(
        "--profile-directory",
        type=Path,
        default=Path.home() / ".veridra" / "browser-profile",
    )
    parser.add_argument("--max-businesses", type=int, default=50)
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


def _is_sponsored(category: str) -> bool:
    return category.strip().casefold() in {"sponsored", "ad", "advertisement"}


def _load_discovery_contexts(path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("captured_observations.json"))
    if not isinstance(raw, list):
        raise ValueError("captured_observations.json must contain a list.")

    contexts: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        business = item.get("business")
        if not isinstance(business, dict):
            continue
        name = _text(business.get("name"))
        source_url = _text(business.get("source_url"))
        category = _text(business.get("category"))
        if not name or not source_url or _is_sponsored(category):
            continue
        contexts.append(
            {
                "business_name": name,
                "source_url": source_url,
                "website": _text(business.get("website")) or None,
                "category": category,
                "signals": {
                    "rating": _number(business.get("rating")),
                    "review_count": _integer(business.get("review_count")),
                },
                "discovery_result_rank": item.get("result_rank"),
                "query_text": item.get("query_text"),
            }
        )
    return contexts


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_businesses < 1 or args.max_businesses > 200:
        raise ValueError("max-businesses must be between 1 and 200.")

    input_path = args.input or _latest(args.downloads, "VERIDRA_DISCOVERY_*.zip")
    if input_path is None or not input_path.is_file():
        raise FileNotFoundError("No VERIDRA discovery ZIP was found.")

    contexts = _load_discovery_contexts(input_path)[: args.max_businesses]
    if not contexts:
        raise ValueError("The discovery ZIP contains no eligible Google Maps source URLs.")

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
        for context in contexts:
            try:
                evidence = _capture(page, context)
                payload = evidence.model_dump(mode="json")
                payload["discovery_result_rank"] = context.get("discovery_result_rank")
                payload["query_text"] = context.get("query_text")
                collected.append(payload)
            except Exception as exc:
                failure = _failed(context, exc)
                failure["discovery_result_rank"] = context.get("discovery_result_rank")
                failure["query_text"] = context.get("query_text")
                collected.append(failure)
        browser.close()

    ok_count = sum(1 for row in collected if row.get("collection_status") == "ok")
    without_website = sum(1 for context in contexts if not context.get("website"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output = args.output_directory / f"VERIDRA_GBP_DISCOVERY_EVIDENCE_{stamp}.zip"
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_discovery": input_path.name,
        "businesses_requested": len(contexts),
        "businesses_without_website_requested": without_website,
        "businesses_collected": ok_count,
        "businesses_failed": len(contexts) - ok_count,
        "method": "broad Google Maps discovery followed by visible public detail-page observation",
        "absence_rule": (
            "An unobserved field is a collection result, not proof that the business owner "
            "failed to configure the Google Business Profile field."
        ),
        "review_rule": (
            "Review text, recency and owner-response analysis remain in Review Intelligence; "
            "this layer does not duplicate or infer them."
        ),
        "persistence": "none",
        "outreach": "none",
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr(
            "gbp_evidence.json",
            json.dumps(collected, indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "README.md",
            "# VERIDRA GBP Discovery Evidence\n\n"
            "Read-only enrichment of broad Google Maps discovery observations. Businesses are "
            "eligible whether or not a website was observed during discovery. Sponsored rows are "
            "excluded. The pack preserves discovery rank/query provenance and public GBP evidence. "
            "No prospect state is mutated and no outreach is sent.\n",
        )

    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output),
                "businesses_requested": len(contexts),
                "businesses_without_website_requested": without_website,
                "businesses_collected": ok_count,
                "businesses_failed": len(contexts) - ok_count,
                "persistence": "none",
                "outreach": "none",
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
