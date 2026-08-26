from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import zipfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SCHEMA_VERSION = 1
_DEFAULT_MAX_BUSINESSES = 10
_DEFAULT_PER_STRATEGY = 20
_STRATEGIES = ("newest", "lowest", "highest")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safe_name(value: str) -> str:
    clean = "".join(char if char.isalnum() else "-" for char in value).strip("-")
    return "-".join(part for part in clean.split("-") if part)[:100] or "prospect"


def _latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _read_json(archive: zipfile.ZipFile, name: str) -> object:
    try:
        return json.loads(archive.read(name))
    except KeyError as exc:
        raise ValueError(f"Required file is missing from ZIP: {name}") from exc


def _load_competitive(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    with zipfile.ZipFile(path) as archive:
        manifest = _read_json(archive, "manifest.json")
        rows = _read_json(archive, "competitive_context.json")
    if not isinstance(manifest, dict) or not isinstance(rows, list):
        raise ValueError("Competitive context ZIP has an invalid structure.")
    return manifest, [item for item in rows if isinstance(item, dict)]


def _google_maps_url(value: object) -> str:
    raw = _text(value)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if "google." not in parsed.netloc.casefold() and "maps.app.goo.gl" not in parsed.netloc.casefold():
        return ""
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("hl", "en")
    return urlunsplit((parsed.scheme or "https", parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _candidate_rows(rows: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    def key(row: dict[str, object]) -> tuple[int, int, str]:
        opportunities = row.get("webify_opportunities")
        visual_count = row.get("website_visual_evidence_count")
        return (
            0 if isinstance(opportunities, list) and opportunities else 1,
            -int(visual_count) if isinstance(visual_count, int) else 0,
            _text(row.get("business_name")).casefold(),
        )

    eligible = [row for row in rows if _google_maps_url(row.get("source_url"))]
    return sorted(eligible, key=key)[:limit]


def _stable_review_id(*, business_name: str, source_review_id: str, text: str, rating: int | None) -> str:
    if source_review_id:
        token = source_review_id
    else:
        token = f"{business_name}|{rating}|{text}"
    digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()[:20]
    return f"review:{_safe_name(business_name)}:{digest}"


def _relative_date(value: str, *, observed_at: datetime) -> str | None:
    clean = " ".join(value.casefold().replace("edited", "").split())
    if not clean:
        return None
    if clean in {"today", "just now"}:
        return observed_at.date().isoformat()
    if clean in {"yesterday", "a day ago", "1 day ago"}:
        return (observed_at - timedelta(days=1)).date().isoformat()
    match = re.search(r"(?:a|1)\s+(day|week|month|year)\s+ago", clean)
    if match:
        amount = 1
        unit = match.group(1)
    else:
        match = re.search(r"(\d+)\s+(day|week|month|year)s?\s+ago", clean)
        if not match:
            return None
        amount = int(match.group(1))
        unit = match.group(2)
    days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * amount
    return (observed_at - timedelta(days=days)).date().isoformat()


def _rating_from_label(label: str) -> int | None:
    match = re.search(r"([1-5](?:\.0)?)\s+star", label.casefold())
    if not match:
        return None
    return int(float(match.group(1)))


def _review_from_card(card: object, *, business_name: str, strategy: str, observed_at: datetime) -> dict[str, object] | None:
    try:
        source_review_id = _text(card.get_attribute("data-review-id"))
        text_node = card.locator(".wiI7pd").first
        body = text_node.inner_text().strip() if text_node.count() else ""
        if not body:
            body = _text(card.get_attribute("aria-label"))
        star = card.locator("span.kvMYJc, span[role='img']").first
        star_label = star.get_attribute("aria-label") if star.count() else ""
        rating = _rating_from_label(_text(star_label))
        date_node = card.locator(".rsqaWe").first
        date_text = date_node.inner_text().strip() if date_node.count() else ""
        owner_node = card.locator(".CDe7pd .wiI7pd, .CDe7pd").first
        owner_response = owner_node.inner_text().strip() if owner_node.count() else ""
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


def _click_reviews(page: object) -> bool:
    selectors = [
        "button[jsaction*='reviewChart']",
        "button[aria-label*='reviews' i]",
        "button:has-text('reviews')",
    ]
    for selector in selectors:
        target = page.locator(selector).first
        if target.count():
            try:
                target.click(timeout=5000)
                page.wait_for_timeout(1200)
                return True
            except Exception:
                continue
    return False


def _choose_sort(page: object, strategy: str) -> bool:
    if strategy == "default":
        return True
    menu_selectors = [
        "button[aria-label*='Sort reviews' i]",
        "button:has-text('Sort')",
    ]
    for selector in menu_selectors:
        button = page.locator(selector).first
        if not button.count():
            continue
        try:
            button.click(timeout=4000)
            page.wait_for_timeout(300)
            labels = {
                "newest": "Newest",
                "lowest": "Lowest rating",
                "highest": "Highest rating",
            }
            option = page.get_by_text(labels[strategy], exact=False).first
            if not option.count():
                option = page.get_by_text(strategy.title(), exact=False).first
            if option.count():
                option.click(timeout=4000)
                page.wait_for_timeout(900)
                return True
        except Exception:
            continue
    return False


def _review_cards(page: object) -> object:
    for selector in ("div[data-review-id]", "div.jftiEf"):
        cards = page.locator(selector)
        if cards.count():
            return cards
    return page.locator("div[data-review-id]")


def _collect_strategy(page: object, *, business_name: str, strategy: str, limit: int) -> list[dict[str, object]]:
    if not _choose_sort(page, strategy):
        return []
    observed_at = datetime.now(UTC)
    results: list[dict[str, object]] = []
    seen: set[str] = set()
    stagnant = 0
    while len(results) < limit and stagnant < 3:
        cards = _review_cards(page)
        before = len(results)
        for index in range(cards.count()):
            row = _review_from_card(
                cards.nth(index),
                business_name=business_name,
                strategy=strategy,
                observed_at=observed_at,
            )
            if row is None:
                continue
            evidence_id = _text(row.get("evidence_id"))
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            results.append(row)
            if len(results) >= limit:
                break
        if len(results) == before:
            stagnant += 1
        else:
            stagnant = 0
        try:
            cards.last.scroll_into_view_if_needed(timeout=2500)
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(500)
        except Exception:
            break
    return results[:limit]


def _merge_reviews(groups: Iterable[list[dict[str, object]]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for group in groups:
        for row in group:
            evidence_id = _text(row.get("evidence_id"))
            if not evidence_id:
                continue
            existing = merged.get(evidence_id)
            if existing is None:
                copy = dict(row)
                copy["sample_strategies"] = [_text(row.get("sample_strategy"))]
                merged[evidence_id] = copy
                continue
            strategies = existing.get("sample_strategies")
            if isinstance(strategies, list):
                strategy = _text(row.get("sample_strategy"))
                if strategy and strategy not in strategies:
                    strategies.append(strategy)
    return list(merged.values())


def _statistics(reviews: list[dict[str, object]], *, now: datetime) -> dict[str, object]:
    parsed_dates: list[datetime] = []
    ratings: dict[str, int] = {str(value): 0 for value in range(1, 6)}
    responses = 0
    negative = 0
    negative_responses = 0
    for row in reviews:
        rating = row.get("rating")
        if isinstance(rating, int) and 1 <= rating <= 5:
            ratings[str(rating)] += 1
            if rating <= 3:
                negative += 1
                if row.get("owner_response_present") is True:
                    negative_responses += 1
        if row.get("owner_response_present") is True:
            responses += 1
        raw_date = _text(row.get("approximate_review_date"))
        if raw_date:
            try:
                parsed_dates.append(datetime.fromisoformat(raw_date).replace(tzinfo=UTC))
            except ValueError:
                pass

    def count_days(days: int) -> int:
        cutoff = now - timedelta(days=days)
        return sum(1 for value in parsed_dates if value >= cutoff)

    known_dates = len(parsed_dates)
    count_365 = count_days(365)
    return {
        "sample_size": len(reviews),
        "dated_sample_size": known_dates,
        "sampled_reviews_last_30_days": count_days(30),
        "sampled_reviews_last_90_days": count_days(90),
        "sampled_reviews_last_365_days": count_365,
        "sampled_review_velocity_per_month_365d": round(count_365 / 12, 2),
        "owner_response_rate_sample": round(responses / len(reviews), 3) if reviews else None,
        "negative_review_count_sample": negative,
        "negative_review_response_rate_sample": (
            round(negative_responses / negative, 3) if negative else None
        ),
        "rating_distribution_sample": ratings,
        "scope_note": (
            "All recency, velocity, response-rate and rating-distribution values describe the bounded "
            "sample collected by VERIDRA, not the business's complete review history."
        ),
    }


def collect_reviews(
    *,
    competitive_input: Path,
    output_directory: Path,
    max_businesses: int,
    per_strategy: int,
    profile_directory: Path,
    startup_wait_seconds: float,
) -> Path:
    if max_businesses < 1 or max_businesses > 50:
        raise ValueError("max-businesses must be between 1 and 50.")
    if per_strategy < 1 or per_strategy > 50:
        raise ValueError("per-strategy must be between 1 and 50.")
    source_manifest, rows = _load_competitive(competitive_input)
    candidates = _candidate_rows(rows, max_businesses)
    generated_at = datetime.now(UTC)
    business_results: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []

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
            try:
                page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
                if startup_wait_seconds:
                    time.sleep(startup_wait_seconds)
                if not _click_reviews(page):
                    failures.append({"business_name": business_name, "reason": "reviews_ui_not_found"})
                    continue
                groups = [
                    _collect_strategy(
                        page,
                        business_name=business_name,
                        strategy=strategy,
                        limit=per_strategy,
                    )
                    for strategy in _STRATEGIES
                ]
                reviews = _merge_reviews(groups)
                business_results.append(
                    {
                        "business_name": business_name,
                        "website": row.get("website"),
                        "source_url": source_url,
                        "cohort_member": row.get("cohort_member"),
                        "google_rating": (row.get("signals") or {}).get("rating")
                        if isinstance(row.get("signals"), dict)
                        else None,
                        "google_review_count": (row.get("signals") or {}).get("review_count")
                        if isinstance(row.get("signals"), dict)
                        else None,
                        "statistics": _statistics(reviews, now=generated_at),
                        "reviews": reviews,
                    }
                )
            except Exception as exc:
                detail = " ".join(str(exc).split())[:220]
                failures.append(
                    {
                        "business_name": business_name,
                        "reason": f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__,
                    }
                )
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
        },
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
        archive.writestr("review_evidence.json", json.dumps(business_results, indent=2, ensure_ascii=False))
        archive.writestr("evidence_index.json", json.dumps(evidence_index, indent=2, ensure_ascii=False))
        archive.writestr("cohort_summary.json", json.dumps(cohort_summary, indent=2, ensure_ascii=False))
        archive.writestr(
            "README.md",
            "# VERIDRA Review Intelligence\n\n"
            "Read-only bounded Google Maps review evidence. Statistics describe the collected sample, "
            "not the complete review history. VERIDRA performs no sentiment, theme, authenticity or "
            "commercial interpretation here; those jobs belong to the AI enrichment layer.\n",
        )
    output.write_bytes(buffer.getvalue())
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-review-intelligence")
    parser.add_argument("--competitive-input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-businesses", type=int, default=_DEFAULT_MAX_BUSINESSES)
    parser.add_argument("--per-strategy", type=int, default=_DEFAULT_PER_STRATEGY)
    parser.add_argument("--startup-wait-seconds", type=float, default=2.0)
    parser.add_argument(
        "--profile-directory",
        type=Path,
        default=Path.home() / ".veridra" / "browser-profile",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    competitive = args.competitive_input or _latest(args.downloads, "VERIDRA_COMPETITIVE_*.zip")
    if competitive is None:
        raise FileNotFoundError("No VERIDRA competitive-context ZIP was found.")
    print("[Veridra] Collecting bounded review intelligence from Google Maps...")
    output = collect_reviews(
        competitive_input=competitive,
        output_directory=args.output_directory,
        max_businesses=args.max_businesses,
        per_strategy=args.per_strategy,
        profile_directory=args.profile_directory,
        startup_wait_seconds=args.startup_wait_seconds,
    )
    print(json.dumps({"output": str(output), "persistence": "none", "outreach": "none"}, indent=2))
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
