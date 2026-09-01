from __future__ import annotations

import argparse
import json
import zipfile
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from .review_intelligence_cli import _latest, _text

_PROHIBITED_INTERPRETATION_KEYS = {
    "sentiment",
    "sentiment_score",
    "themes",
    "review_themes",
    "fake_review",
    "fake_review_score",
    "authenticity_score",
}


def _read_json(archive: zipfile.ZipFile, name: str) -> object:
    try:
        return json.loads(archive.read(name))
    except KeyError as exc:
        raise ValueError(f"Required file is missing from ZIP: {name}") from exc


def _load_review_pack(
    path: Path,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        manifest = _read_json(archive, "manifest.json")
        evidence = _read_json(archive, "review_evidence.json")
        evidence_index = _read_json(archive, "evidence_index.json")
    if not isinstance(manifest, dict):
        raise ValueError("Review Intelligence manifest is invalid.")
    if not isinstance(evidence, list):
        raise ValueError("Review Intelligence evidence is invalid.")
    if not isinstance(evidence_index, dict):
        raise ValueError("Review Intelligence evidence index is invalid.")
    rows = [item for item in evidence if isinstance(item, dict)]
    return manifest, rows, evidence_index


def _load_ai_index(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    with zipfile.ZipFile(path) as archive:
        index = _read_json(archive, "evidence_index.json")
    if not isinstance(index, dict):
        raise ValueError("AI export evidence index is invalid.")
    return index


def _iso_date_or_none(value: object) -> bool:
    raw = _text(value)
    if not raw:
        return True
    try:
        date.fromisoformat(raw)
    except ValueError:
        return False
    return True


def _strategy_set(review: dict[str, object]) -> set[str]:
    strategies = review.get("sample_strategies")
    output = {
        _text(item)
        for item in strategies
        if isinstance(item, str) and _text(item)
    } if isinstance(strategies, list) else set()
    strategy = _text(review.get("sample_strategy"))
    if strategy:
        output.add(strategy)
    return output


def _all_reviews(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    reviews: list[dict[str, object]] = []
    for business in rows:
        raw = business.get("reviews")
        if isinstance(raw, list):
            reviews.extend(item for item in raw if isinstance(item, dict))
    return reviews


def _contains_prohibited_interpretation(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in _PROHIBITED_INTERPRETATION_KEYS:
                return True
            if _contains_prohibited_interpretation(child):
                return True
    elif isinstance(value, list):
        return any(_contains_prohibited_interpretation(item) for item in value)
    return False


def validate_review_intelligence(
    review_pack: Path,
    *,
    ai_export: Path | None = None,
) -> dict[str, object]:
    manifest, businesses, evidence_index = _load_review_pack(review_pack)
    reviews = _all_reviews(businesses)
    ai_index = _load_ai_index(ai_export)

    ids = [_text(item.get("evidence_id")) for item in reviews]
    nonempty_ids = [item for item in ids if item]
    unique_ids = set(nonempty_ids)
    ratings_ok = all(
        rating is None or (isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5)
        for rating in (item.get("rating") for item in reviews)
    )
    dates_ok = all(
        _iso_date_or_none(item.get("approximate_review_date"))
        and _iso_date_or_none(item.get("approximate_owner_response_date"))
        for item in reviews
    )
    indexed_ok = bool(nonempty_ids) and all(item in evidence_index for item in nonempty_ids)
    unique_ok = len(nonempty_ids) == len(unique_ids)

    sampling = manifest.get("sampling")
    sampling_dict = sampling if isinstance(sampling, dict) else {}
    per_strategy = sampling_dict.get("per_strategy_limit")
    per_strategy_limit = per_strategy if isinstance(per_strategy, int) else None
    strategy_counts: dict[str, int] = {"newest": 0, "lowest": 0, "highest": 0}
    for review in reviews:
        for strategy in _strategy_set(review):
            if strategy in strategy_counts:
                strategy_counts[strategy] += 1
    bounded_ok = per_strategy_limit is not None and all(
        value <= per_strategy_limit * max(1, len(businesses))
        for value in strategy_counts.values()
    )

    nonempty_businesses = sum(
        1
        for business in businesses
        if isinstance(business.get("reviews"), list) and bool(business.get("reviews"))
    )
    manifest_count = manifest.get("review_evidence_items")
    manifest_count_ok = isinstance(manifest_count, int) and manifest_count == len(evidence_index)
    no_interpretation = not _contains_prohibited_interpretation(
        {"businesses": businesses, "manifest": manifest}
    )

    ai_review_refs: list[str] = []
    if ai_index is not None:
        ai_review_refs = [
            evidence_id
            for evidence_id, entry in ai_index.items()
            if isinstance(entry, dict) and entry.get("type") == "google_review"
        ]
    ai_integration_ok: bool | None = None
    if ai_index is not None:
        ai_integration_ok = bool(ai_review_refs) and any(
            evidence_id in unique_ids for evidence_id in ai_review_refs
        )

    checks: dict[str, bool | None] = {
        "nonzero_review_evidence": len(reviews) > 0,
        "business_with_nonempty_sample": nonempty_businesses > 0,
        "manifest_evidence_count_matches_index": manifest_count_ok,
        "ratings_plausible": ratings_ok,
        "approximate_dates_parse": dates_ok,
        "evidence_ids_present_and_indexed": indexed_ok,
        "evidence_ids_unique": unique_ok,
        "sampling_bounded": bounded_ok,
        "no_deterministic_interpretation_fields": no_interpretation,
        "ai_export_contains_traceable_review_evidence": ai_integration_ok,
    }
    required_results = [value for value in checks.values() if value is not None]
    passed = bool(required_results) and all(required_results)

    return {
        "passed": passed,
        "review_pack": str(review_pack),
        "ai_export": str(ai_export) if ai_export is not None else None,
        "review_evidence_items": len(reviews),
        "businesses_with_review_evidence": nonempty_businesses,
        "evidence_index_items": len(evidence_index),
        "strategy_counts": strategy_counts,
        "per_strategy_limit": per_strategy_limit,
        "checks": checks,
        "manual_boundary": (
            "This validator proves artifact semantics only. A live Google Maps collection still "
            "requires the operator run and any Google consent/sign-in/CAPTCHA interruption."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-review-intelligence-acceptance")
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--review-pack", type=Path)
    parser.add_argument("--ai-export", type=Path)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    review_pack = args.review_pack or _latest(
        args.downloads,
        "VERIDRA_REVIEW_INTELLIGENCE_*.zip",
    )
    if review_pack is None:
        raise FileNotFoundError("No VERIDRA Review Intelligence ZIP was found.")
    ai_export = args.ai_export
    report = validate_review_intelligence(review_pack, ai_export=ai_export)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] is True else 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
