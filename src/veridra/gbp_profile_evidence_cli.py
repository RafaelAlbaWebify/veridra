from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .gbp_profile_evidence import (
    GbpProfileEvidence,
    classify_booking_links,
    unique_external_links,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-gbp-profile-evidence")
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


def _load_contexts(path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("competitive_context.json"))
    if not isinstance(raw, list):
        raise ValueError("competitive_context.json must contain a list.")
    return [item for item in raw if isinstance(item, dict)]


def _safe_inner_text(locator: Any) -> str:
    try:
        if int(locator.count()) < 1:
            return ""
        return " ".join(str(locator.first.inner_text(timeout=1_500)).split())
    except Exception:
        return ""


def _first_text(page: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        value = _safe_inner_text(page.locator(selector))
        if value:
            return value
    return ""


def _profile_item_ids(page: Any) -> tuple[str, ...]:
    try:
        values = page.eval_on_selector_all(
            "[data-item-id]",
            "els => els.map(el => el.getAttribute('data-item-id')).filter(Boolean)",
        )
    except Exception:
        return ()
    if not isinstance(values, list):
        return ()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        if clean and clean not in result:
            result.append(clean[:300])
    return tuple(result[:500])


def _action_rows(page: Any) -> list[tuple[str, str, str]]:
    try:
        rows = page.eval_on_selector_all(
            "a[href]",
            """
            els => els.map(el => ({
              href: el.href || '',
              label: el.getAttribute('aria-label') || el.innerText || '',
              item_id: el.getAttribute('data-item-id') || ''
            }))
            """,
        )
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    result: list[tuple[str, str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result.append(
            (
                _text(row.get("href")),
                _text(row.get("label")),
                _text(row.get("item_id")),
            )
        )
    return result


def _action_labels(page: Any) -> tuple[str, ...]:
    try:
        values = page.eval_on_selector_all(
            "button[aria-label],a[aria-label]",
            "els => els.map(el => el.getAttribute('aria-label')).filter(Boolean)",
        )
    except Exception:
        return ()
    if not isinstance(values, list):
        return ()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        if clean and clean not in result:
            result.append(clean[:500])
    return tuple(result[:300])


def _photo_labels(labels: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(label for label in labels if "photo" in label.casefold())[:200]


def _website(page: Any) -> str | None:
    try:
        locator = page.locator('a[data-item-id="authority"][href]')
        if int(locator.count()) < 1:
            return None
        href = locator.first.get_attribute("href")
    except Exception:
        return None
    return href if isinstance(href, str) and href.startswith(("http://", "https://")) else None


def _category(page: Any) -> str:
    selectors = (
        'button[jsaction*="category"]',
        '[data-item-id="category"]',
    )
    return _first_text(page, selectors)


def _signals(context: dict[str, object]) -> tuple[float | None, int | None]:
    raw = context.get("signals")
    signals = raw if isinstance(raw, dict) else {}
    return _number(signals.get("rating")), _integer(signals.get("review_count"))


def _capture(page: Any, context: dict[str, object]) -> GbpProfileEvidence:
    name = _text(context.get("business_name"))
    source_url = _text(context.get("source_url"))
    if not name or not source_url:
        raise ValueError("Business name and Google Maps source URL are required.")

    page.goto(source_url, wait_until="domcontentloaded", timeout=15_000)
    page.wait_for_timeout(900)

    item_ids = _profile_item_ids(page)
    actions = _action_rows(page)
    labels = _action_labels(page)
    rating, review_count = _signals(context)
    website = _website(page) or _text(context.get("website")) or None

    return GbpProfileEvidence.model_validate(
        {
            "business_name": name,
            "source_url": source_url,
            "observed_at": datetime.now(UTC),
            "collection_status": "ok",
            "category": _category(page) or _text(context.get("category")),
            "rating": rating,
            "review_count": review_count,
            "website_url": website,
            "address_text": _first_text(
                page,
                (
                    'button[data-item-id="address"]',
                    '[data-item-id="address"]',
                ),
            ),
            "phone_text": _first_text(
                page,
                (
                    'button[data-item-id^="phone:tel:"]',
                    '[data-item-id^="phone:tel:"]',
                ),
            ),
            "hours_text": _first_text(
                page,
                (
                    'button[data-item-id="oh"]',
                    '[data-item-id="oh"]',
                ),
            ),
            "booking_links": classify_booking_links(actions),
            "external_action_links": unique_external_links(actions),
            "profile_item_ids": item_ids,
            "photo_control_labels": _photo_labels(labels),
            "raw_action_labels": labels,
        }
    )


def _failed(context: dict[str, object], error: Exception) -> dict[str, object]:
    detail = re.sub(r"\s+", " ", str(error)).strip()[:500]
    return {
        "business_name": _text(context.get("business_name")),
        "source_url": _text(context.get("source_url")),
        "collection_status": "failed",
        "error_type": type(error).__name__,
        "error": detail,
    }


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_businesses < 1 or args.max_businesses > 200:
        raise ValueError("max-businesses must be between 1 and 200.")

    input_path = args.input or _latest(args.downloads, "VERIDRA_COMPETITIVE_*.zip")
    if input_path is None or not input_path.is_file():
        raise FileNotFoundError("No VERIDRA competitive-context ZIP was found.")

    contexts = [
        item
        for item in _load_contexts(input_path)
        if item.get("cohort_member") is not False and _text(item.get("source_url"))
    ][: args.max_businesses]
    if not contexts:
        raise ValueError("The competitive-context ZIP contains no Google Maps source URLs.")

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
                collected.append(evidence.model_dump(mode="json"))
            except Exception as exc:
                collected.append(_failed(context, exc))
        browser.close()

    ok_count = sum(1 for row in collected if row.get("collection_status") == "ok")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output = args.output_directory / f"VERIDRA_GBP_EVIDENCE_{stamp}.zip"
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_competitive_context": input_path.name,
        "businesses_requested": len(contexts),
        "businesses_collected": ok_count,
        "businesses_failed": len(contexts) - ok_count,
        "method": "visible public Google Maps detail-page observation",
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
            "# VERIDRA Google Business Profile Evidence\n\n"
            "Read-only bounded observation of fields exposed by public Google Maps detail pages. "
            "The pack preserves observed profile item IDs and action labels alongside normalized "
            "website, address, phone, hours, booking/action-link and photo-control evidence. "
            "Absence means not observed in this run, not proven unconfigured. Review text and "
            "owner-response analysis remain authoritative in Review Intelligence. No prospect "
            "state is mutated and no outreach is sent.\n",
        )

    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output),
                "businesses_requested": len(contexts),
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
