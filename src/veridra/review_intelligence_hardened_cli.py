from __future__ import annotations

import io
import json
import time
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .review_intelligence_cli import (
    SCHEMA_VERSION as BASE_SCHEMA_VERSION,
    _candidate_rows,
    _google_maps_url,
    _latest,
    _load_competitive,
    _merge_reviews,
    _rating_from_label,
    _relative_date,
    _stable_review_id,
    _statistics,
    _text,
    build_parser as _base_parser,
)

SCHEMA_VERSION = BASE_SCHEMA_VERSION + 1
_STRATEGIES = ("newest", "lowest", "highest")
_REVIEW_CARD_SELECTORS = (
    "div.jftiEf[data-review-id]",
    "div[data-review-id]",
    "div.jftiEf",
)
_REVIEW_TAB_SELECTORS = (
    "button[role='tab'][aria-label*='Reviews' i]",
    "[role='tab'][aria-label*='Reviews' i]",
    "button[data-tab-index='1']",
    "button[jsaction*='reviewChart']",
    "button[aria-label*='reviews' i]",
    "button:has-text('Reviews')",
)
_SORT_BUTTON_SELECTORS = (
    "button[aria-label*='Sort reviews' i]",
    "button[aria-label^='Sort' i]",
    "button[data-value='Sort']",
    "button:has-text('Sort')",
)
_SCROLL_PANEL_SELECTORS = (
    "div.m6QErb.DxyBCb.kA9KIf.dS8AEf",
    "div[role='main'] div[tabindex='-1']",
    "div.m6QErb",
)


def _safe_inner_text(locator: Any) -> str:
    try:
        if locator.count():
            return _text(locator.first.inner_text(timeout=2000))
    except Exception:
        pass
    return ""


def _first_text(card: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        value = _safe_inner_text(card.locator(selector))
        if value:
            return value
    return ""


def _first_attribute(card: Any, selectors: tuple[str, ...], attribute: str) -> str:
    for selector in selectors:
        try:
            node = card.locator(selector).first
            if not node.count():
                continue
            value = _text(node.get_attribute(attribute))
            if value:
                return value
        except Exception:
            continue
    return ""


def _review_from_card(
    card: Any,
    *,
    business_name: str,
    strategy: str,
    observed_at: datetime,
) -> dict[str, object] | None:
    try:
        source_review_id = _text(card.get_attribute("data-review-id"))
        body = _first_text(
            card,
            (
                ".MyEned .wiI7pd",
                ".wiI7pd",
                ".MyEned",
            ),
        )
        star_label = _first_attribute(
            card,
            (
                "span.kvMYJc",
                "span[role='img'][aria-label*='star' i]",
                "div[role='img'][aria-label*='star' i]",
                "[aria-label*='star' i]",
            ),
            "aria-label",
        )
        rating = _rating_from_label(star_label)
        date_text = _first_text(card, (".rsqaWe", "span.rsqaWe", ".DU9Pgb .rsqaWe"))
        owner_response = _first_text(
            card,
            (
                ".CDe7pd .wiI7pd",
                ".CDe7pd",
            ),
        )
        if not body and rating is None:
            return None
        evidence_id = _stable_review_id(
            business_name=business_name,
            source_review_id=source_review_id,
            text=body,
            rating=rating,
        )
        return {
            "evidence_id": evidence_id,
            "source_review_id": source_review_id or None,
            "rating": rating,
            "text": body or None,
            "date_text": date_text or None,
            "approximate_review_date": _relative_date(date_text, observed_at=observed_at),
            "owner_response_text": owner_response or None,
            "owner_response_present": bool(owner_response),
            "sample_strategy": strategy,
            "observed_at": observed_at.isoformat(),
        }
    except Exception:
        return None


def _review_cards(page: Any) -> tuple[Any, str, int]:
    for selector in _REVIEW_CARD_SELECTORS:
        try:
            cards = page.locator(selector)
            count = cards.count()
            if count:
                return cards, selector, count
        except Exception:
            continue
    cards = page.locator(_REVIEW_CARD_SELECTORS[0])
    return cards, _REVIEW_CARD_SELECTORS[0], 0


def _wait_for_review_cards(page: Any, *, timeout_ms: int = 7000) -> tuple[Any, str, int]:
    deadline = time.monotonic() + timeout_ms / 1000
    last = _review_cards(page)
    while time.monotonic() < deadline:
        last = _review_cards(page)
        if last[2] > 0:
            return last
        page.wait_for_timeout(250)
    return last


def _click_reviews(page: Any) -> tuple[bool, str, int]:
    existing = _review_cards(page)
    if existing[2] > 0:
        return True, "already-visible", existing[2]
    for selector in _REVIEW_TAB_SELECTORS:
        try:
            target = page.locator(selector).first
            if not target.count():
                continue
            target.click(timeout=5000)
            page.wait_for_timeout(900)
            _, _, count = _wait_for_review_cards(page)
            if count:
                return True, selector, count
        except Exception:
            continue
    _, _, count = _wait_for_review_cards(page, timeout_ms=2500)
    return count > 0, "", count


def _sort_labels(strategy: str) -> tuple[str, ...]:
    return {
        "newest": ("Newest", "Most recent"),
        "lowest": ("Lowest rating", "Lowest"),
        "highest": ("Highest rating", "Highest"),
    }[strategy]


def _choose_sort(page: Any, strategy: str) -> dict[str, object]:
    result: dict[str, object] = {
        "requested": strategy,
        "selected": False,
        "button_selector": None,
        "option_label": None,
        "fallback": None,
    }
    for selector in _SORT_BUTTON_SELECTORS:
        try:
            button = page.locator(selector).first
            if not button.count():
                continue
            button.click(timeout=4000)
            page.wait_for_timeout(350)
            for label in _sort_labels(strategy):
                candidates = (
                    page.get_by_role("menuitemradio", name=label, exact=False),
                    page.get_by_role("menuitem", name=label, exact=False),
                    page.get_by_text(label, exact=False),
                )
                for candidate in candidates:
                    option = candidate.first
                    if not option.count():
                        continue
                    option.click(timeout=4000)
                    page.wait_for_timeout(900)
                    result.update(
                        {
                            "selected": True,
                            "button_selector": selector,
                            "option_label": label,
                        }
                    )
                    return result
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            continue
    if strategy == "newest":
        result["fallback"] = "visible-current-order"
    else:
        result["fallback"] = "sort-unavailable"
    return result


def _scroll_review_panel(page: Any, cards: Any) -> bool:
    try:
        if cards.count():
            cards.last.scroll_into_view_if_needed(timeout=2500)
    except Exception:
        pass
    for selector in _SCROLL_PANEL_SELECTORS:
        try:
            panel = page.locator(selector).last
            if not panel.count():
                continue
            panel.evaluate("node => node.scrollBy(0, Math.max(1200, node.clientHeight * 0.9))")
            page.wait_for_timeout(550)
            return True
        except Exception:
            continue
    try:
        page.mouse.wheel(0, 1600)
        page.wait_for_timeout(550)
        return True
    except Exception:
        return False


def _collect_strategy(
    page: Any,
    *,
    business_name: str,
    strategy: str,
    limit: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    sort = _choose_sort(page, strategy)
    diagnostics: dict[str, object] = {
        "strategy": strategy,
        "sort": sort,
        "card_selector": None,
        "max_cards_seen": 0,
        "rows_collected": 0,
    }
    if strategy != "newest" and sort["selected"] is not True:
        return [], diagnostics
    effective_strategy = strategy if sort["selected"] is True else "visible-default"
    observed_at = datetime.now(UTC)
    results: list[dict[str, object]] = []
    seen: set[str] = set()
    stagnant = 0
    while len(results) < limit and stagnant < 3:
        cards, selector, count = _wait_for_review_cards(page, timeout_ms=2500)
        diagnostics["card_selector"] = selector
        diagnostics["max_cards_seen"] = max(int(diagnostics["max_cards_seen"]), count)
        before = len(results)
        for index in range(count):
            row = _review_from_card(
                cards.nth(index),
                business_name=business_name,
                strategy=effective_strategy,
                observed_at=observed_at,
            )
            if row is None:
                continue
            evidence_id = _text(row.get("evidence_id"))
            if not evidence_id or evidence_id in seen:
                continue
            seen.add(evidence_id)
            results.append(row)
            if len(results) >= limit:
                break
        stagnant = stagnant + 1 if len(results) == before else 0
        if len(results) < limit and not _scroll_review_panel(page, cards):
            break
    diagnostics["rows_collected"] = len(results)
    return results[:limit], diagnostics


def _success_state(reviews: list[dict[str, object]]) -> str:
    return "review_evidence_collected" if reviews else "review_evidence_empty"


def collect_reviews(
    *,
    competitive_input: Path,
    output_directory: Path,
    max_businesses: int,
    per_strategy: int,
    profile_directory: Path,
    startup_wait_seconds: float,
) -> tuple[Path, int]:
    if max_businesses < 1 or max_businesses > 50:
        raise ValueError("max-businesses must be between 1 and 50.")
    if per_strategy < 1 or per_strategy > 50:
        raise ValueError("per-strategy must be between 1 and 50.")
    source_manifest, rows = _load_competitive(competitive_input)
    candidates = _candidate_rows(rows, max_businesses)
    generated_at = datetime.now(UTC)
    business_results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for review intelligence.") from exc

    profile_directory.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_directory), headless=False
        )
        page = context.pages[0] if context.pages else context.new_page()
        for row in candidates:
            business_name = _text(row.get("business_name"))
            source_url = _google_maps_url(row.get("source_url"))
            if not source_url:
                continue
            business_diag: dict[str, object] = {
                "business_name": business_name,
                "source_url": source_url,
                "reviews_click_selector": None,
                "initial_review_cards": 0,
                "strategies": [],
                "status": "pending",
            }
            try:
                page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
                if startup_wait_seconds:
                    time.sleep(startup_wait_seconds)
                opened, click_selector, initial_count = _click_reviews(page)
                business_diag["reviews_click_selector"] = click_selector or None
                business_diag["initial_review_cards"] = initial_count
                if not opened:
                    business_diag["status"] = "reviews_ui_not_found"
                    failures.append(
                        {"business_name": business_name, "reason": "reviews_ui_not_found"}
                    )
                    diagnostics.append(business_diag)
                    continue
                groups: list[list[dict[str, object]]] = []
                strategy_diagnostics: list[dict[str, object]] = []
                for strategy in _STRATEGIES:
                    group, strategy_diag = _collect_strategy(
                        page,
                        business_name=business_name,
                        strategy=strategy,
                        limit=per_strategy,
                    )
                    groups.append(group)
                    strategy_diagnostics.append(strategy_diag)
                business_diag["strategies"] = strategy_diagnostics
                reviews = _merge_reviews(groups)
                state = _success_state(reviews)
                business_diag["status"] = state
                business_diag["deduped_review_count"] = len(reviews)
                if not reviews:
                    failures.append(
                        {
                            "business_name": business_name,
                            "reason": "review_evidence_empty",
                            "initial_review_cards": initial_count,
                        }
                    )
                    diagnostics.append(business_diag)
                    continue
                signals = row.get("signals")
                signal_dict = signals if isinstance(signals, dict) else {}
                business_results.append(
                    {
                        "business_name": business_name,
                        "website": row.get("website"),
                        "source_url": source_url,
                        "cohort_member": row.get("cohort_member"),
                        "google_rating": signal_dict.get("rating"),
                        "google_review_count": signal_dict.get("review_count"),
                        "statistics": _statistics(reviews, now=generated_at),
                        "reviews": reviews,
                    }
                )
                diagnostics.append(business_diag)
            except Exception as exc:
                detail = " ".join(str(exc).split())[:220]
                reason = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
                business_diag["status"] = "collector_exception"
                business_diag["exception"] = reason
                failures.append({"business_name": business_name, "reason": reason})
                diagnostics.append(business_diag)
        context.close()

    evidence_index: dict[str, dict[str, object]] = {}
    for business in business_results:
        name = _text(business.get("business_name"))
        reviews = business.get("reviews")
        if not isinstance(reviews, list):
            continue
        for review in reviews:
            if not isinstance(review, dict):
                continue
            evidence_id = _text(review.get("evidence_id"))
            if evidence_id:
                evidence_index[evidence_id] = {
                    "business_name": name,
                    "type": "google_review",
                    "rating": review.get("rating"),
                    "approximate_review_date": review.get("approximate_review_date"),
                    "sample_strategies": review.get("sample_strategies"),
                }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / f"VERIDRA_REVIEW_INTELLIGENCE_{stamp}.zip"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "source_competitive_context": competitive_input.name,
        "source_competitive_schema": source_manifest.get("schema_version"),
        "businesses_requested": len(candidates),
        "businesses_with_review_evidence": len(business_results),
        "businesses_failed": len(failures),
        "review_evidence_items": len(evidence_index),
        "sampling": {
            "strategies": list(_STRATEGIES),
            "per_strategy_limit": per_strategy,
            "max_businesses": max_businesses,
            "newest_fallback_rule": (
                "If Google exposes reviews but the sort menu cannot be selected, the current visible "
                "order may be collected only as visible-default and is never mislabeled newest."
            ),
        },
        "success_rule": "a business counts as review evidence only when at least one review row is captured",
        "selector_diagnostics": "diagnostics.json",
        "interpretation": "none; VERIDRA records deterministic review evidence and sample statistics only",
        "persistence": "none",
        "outreach": "none",
    }
    cohort_summary = {
        "businesses": [
            {
                "business_name": item["business_name"],
                "google_rating": item.get("google_rating"),
                "google_review_count": item.get("google_review_count"),
                "statistics": item["statistics"],
            }
            for item in business_results
        ],
        "failures": failures,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr(
            "review_evidence.json", json.dumps(business_results, indent=2, ensure_ascii=False)
        )
        archive.writestr(
            "evidence_index.json", json.dumps(evidence_index, indent=2, ensure_ascii=False)
        )
        archive.writestr(
            "cohort_summary.json", json.dumps(cohort_summary, indent=2, ensure_ascii=False)
        )
        archive.writestr("diagnostics.json", json.dumps(diagnostics, indent=2, ensure_ascii=False))
        archive.writestr(
            "README.md",
            "# VERIDRA Review Intelligence\n\n"
            "Read-only bounded Google Maps review evidence. A business is counted as successful only "
            "when at least one review row is captured. Statistics describe the collected sample, not "
            "the complete review history. Selector/sort diagnostics are preserved in diagnostics.json. "
            "VERIDRA performs no sentiment, theme, authenticity or commercial interpretation here.\n",
        )
    output.write_bytes(buffer.getvalue())
    return output, len(evidence_index)


def build_parser() -> Any:
    return _base_parser()


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    competitive = args.competitive_input or _latest(args.downloads, "VERIDRA_COMPETITIVE_*.zip")
    if competitive is None:
        raise FileNotFoundError("No VERIDRA competitive-context ZIP was found.")
    print("[Veridra] Collecting hardened bounded review intelligence from Google Maps...")
    output, evidence_count = collect_reviews(
        competitive_input=competitive,
        output_directory=args.output_directory,
        max_businesses=args.max_businesses,
        per_strategy=args.per_strategy,
        profile_directory=args.profile_directory,
        startup_wait_seconds=args.startup_wait_seconds,
    )
    summary = {
        "output": str(output),
        "review_evidence_items": evidence_count,
        "persistence": "none",
        "outreach": "none",
    }
    print(json.dumps(summary, indent=2))
    if evidence_count == 0:
        print(
            "[Veridra] Review evidence validation failed: zero review rows were captured. "
            "Inspect diagnostics.json in the output ZIP."
        )
        return 2
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
