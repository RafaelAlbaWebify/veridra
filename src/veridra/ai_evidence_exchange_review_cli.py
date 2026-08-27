from __future__ import annotations

import argparse
import json
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from . import ai_evidence_exchange_cli as base
from .review_intelligence_sampling_safe_cli import strategy_safe_statistics

EXPORT_SCHEMA_VERSION = 2
IMPORTED_SCHEMA_VERSION = 2


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _website_key(value: object) -> str:
    text = _text(value)
    if not text:
        return ""
    parsed = urlsplit(text)
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _json_entry(files: dict[str, bytes], name: str) -> object:
    try:
        return json.loads(files[name])
    except KeyError as exc:
        raise ValueError(f"Required file is missing from ZIP: {name}") from exc


def _zip_files(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _rewrite_zip(path: Path, files: dict[str, bytes]) -> None:
    temporary = path.with_suffix(".rewrite.zip")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    temporary.replace(path)


def _load_review_input(path: Path | None) -> tuple[dict[str, object], list[dict[str, object]]]:
    if path is None or not path.is_file():
        return {}, []
    files = _zip_files(path)
    manifest = _json_entry(files, "manifest.json")
    evidence = _json_entry(files, "review_evidence.json")
    if not isinstance(manifest, dict) or not isinstance(evidence, list):
        raise ValueError("Review Intelligence ZIP has an invalid structure.")
    return manifest, [item for item in evidence if isinstance(item, dict)]


def _review_lookup(
    rows: list[dict[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    by_name: dict[str, dict[str, object]] = {}
    by_website: dict[str, dict[str, object]] = {}
    for row in rows:
        name = _text(row.get("business_name")).casefold()
        website = _website_key(row.get("website"))
        if name:
            by_name[name] = row
        if website:
            by_website[website] = row
    return by_name, by_website


def _observed_at(manifest: dict[str, object]) -> datetime:
    raw = _text(manifest.get("generated_at"))
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _review_payload(
    row: dict[str, object],
    *,
    review_manifest: dict[str, object],
    source_name: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    raw_reviews = row.get("reviews")
    reviews = [item for item in raw_reviews if isinstance(item, dict)] if isinstance(raw_reviews, list) else []
    payload = {
        "business_name": row.get("business_name"),
        "website": row.get("website"),
        "source_url": row.get("source_url"),
        "cohort_member": row.get("cohort_member"),
        "google_rating": row.get("google_rating"),
        "google_review_count": row.get("google_review_count"),
        "sampling_safe_statistics": strategy_safe_statistics(
            reviews,
            now=_observed_at(review_manifest),
        ),
        "reviews": reviews,
        "sampling": review_manifest.get("sampling"),
        "source_review_intelligence": source_name,
        "legacy_source_statistics_ignored": True,
        "statistics_rule": (
            "Statistics are recomputed from raw review rows using strategy-safe semantics. Legacy "
            "merged-sample statistics from the source ZIP are not exported as authoritative."
        ),
    }
    return payload, reviews


def _review_contract(contract: dict[str, object]) -> dict[str, object]:
    result = dict(contract)
    prospect_shape = result.get("prospect_shape")
    shape = dict(prospect_shape) if isinstance(prospect_shape, dict) else {}
    shape["review_themes"] = [
        {
            "theme": "plain-language recurring customer theme",
            "sentiment": "positive | negative | mixed",
            "evidence_refs": ["review evidence ids from evidence_index.json"],
            "supporting_review_count": "integer derived only from cited evidence",
        }
    ]
    shape["evidence_connections"] = [
        {
            "connection": "relationship between two or more evidence-backed signals",
            "evidence_refs": ["evidence ids from evidence_index.json"],
            "confidence": "high | medium | low",
        }
    ]
    result["prospect_shape"] = shape
    rules_raw = result.get("rules")
    rules = [item for item in rules_raw if isinstance(item, str)] if isinstance(rules_raw, list) else []
    rules.extend(
        [
            "Every review theme must cite at least one review evidence ID from evidence_index.json.",
            "Every evidence connection must cite the evidence IDs that support the connection.",
            "Do not infer population-level review velocity, overall response rate, or rating distribution from the stratified newest/lowest/highest sample.",
            "Review text, ratings, dates, owner responses, and sample strategies are evidence; AI themes are interpretations and must remain traceable to that evidence.",
        ]
    )
    result["rules"] = rules
    return result


def export_pack(
    *,
    competitive_input: Path,
    visual_input: Path | None,
    review_input: Path | None,
    output_directory: Path,
) -> Path:
    output = base.export_pack(
        competitive_input=competitive_input,
        visual_input=visual_input,
        output_directory=output_directory,
    )
    files = _zip_files(output)
    manifest = _json_entry(files, "manifest.json")
    evidence_index = _json_entry(files, "evidence_index.json")
    contract = _json_entry(files, "AI_RESPONSE_CONTRACT.json")
    if not isinstance(manifest, dict) or not isinstance(evidence_index, dict) or not isinstance(contract, dict):
        raise ValueError("Base AI export ZIP has an invalid structure.")

    review_manifest, review_rows = _load_review_input(review_input)
    by_name, by_website = _review_lookup(review_rows)
    matched_businesses = 0
    review_evidence_items = 0

    context_names = [
        name
        for name in files
        if name.startswith("prospects/") and name.endswith("/competitive_context.json")
    ]
    for context_name in context_names:
        context = _json_entry(files, context_name)
        if not isinstance(context, dict):
            continue
        business_name = _text(context.get("business_name"))
        website = _website_key(context.get("website"))
        review_row = by_website.get(website) or by_name.get(business_name.casefold())
        if review_row is None:
            continue
        payload, reviews = _review_payload(
            review_row,
            review_manifest=review_manifest,
            source_name=review_input.name if review_input is not None else "",
        )
        folder = context_name.rsplit("/", 1)[0]
        files[f"{folder}/review_evidence.json"] = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8")
        matched_businesses += 1
        for review in reviews:
            evidence_id = _text(review.get("evidence_id"))
            if not evidence_id:
                continue
            evidence_index[evidence_id] = {
                "business_name": business_name,
                "type": "google_review",
                "source": review_input.name if review_input is not None else None,
                "rating": review.get("rating"),
                "approximate_review_date": review.get("approximate_review_date"),
                "owner_response_present": review.get("owner_response_present"),
                "sample_strategies": review.get("sample_strategies"),
            }
            review_evidence_items += 1

    manifest["schema_version"] = EXPORT_SCHEMA_VERSION
    manifest["source_review_intelligence"] = review_input.name if review_input is not None else None
    manifest["review_businesses_matched"] = matched_businesses
    manifest["review_evidence_items"] = review_evidence_items
    manifest["review_statistics_rule"] = (
        "sampling-strategy safe; legacy merged-sample population metrics suppressed"
    )
    manifest["evidence_items"] = len(evidence_index)

    files["manifest.json"] = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    files["evidence_index.json"] = json.dumps(
        evidence_index,
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
    files["AI_RESPONSE_CONTRACT.json"] = json.dumps(
        _review_contract(contract),
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
    files["README.md"] = (
        "# VERIDRA AI Evidence Export\n\n"
        "Read-only evidence pack for external AI interpretation. Competitive, visual and bounded "
        "review evidence remains authoritative. Review statistics are recomputed with sampling-safe "
        "semantics; the intentionally stratified newest/lowest/highest sample must not be treated as "
        "the business's complete review population. Return a `VERIDRA_AI_ENRICHMENT_*.zip` following "
        "`AI_RESPONSE_CONTRACT.json`. Commercial claims, review themes and evidence connections must "
        "cite evidence IDs from `evidence_index.json`.\n"
    ).encode("utf-8")
    _rewrite_zip(output, files)
    return output


def _validated_interpretations(
    items: object,
    *,
    known_refs: set[str],
    kind: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    values = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    for item in values:
        refs_raw = item.get("evidence_refs")
        refs = [value for value in refs_raw if isinstance(value, str) and value] if isinstance(refs_raw, list) else []
        unknown = [value for value in refs if value not in known_refs]
        if not refs or unknown:
            copy = dict(item)
            copy["interpretation_type"] = kind
            copy["rejection_reason"] = "missing evidence refs or unknown evidence refs"
            rejected.append(copy)
            continue
        accepted.append(dict(item))
    return accepted, rejected


def import_pack(
    *,
    enrichment_input: Path,
    source_export_input: Path,
    output_directory: Path,
) -> Path:
    output = base.import_pack(
        enrichment_input=enrichment_input,
        source_export_input=source_export_input,
        output_directory=output_directory,
    )
    files = _zip_files(output)
    source_files = _zip_files(source_export_input)
    evidence_index = _json_entry(source_files, "evidence_index.json")
    manifest = _json_entry(files, "manifest.json")
    report = _json_entry(files, "validation_report.json")
    normalized = _json_entry(files, "normalized_enrichment.json")
    if not isinstance(evidence_index, dict) or not isinstance(manifest, dict):
        raise ValueError("AI evidence exchange ZIP has an invalid structure.")
    if not isinstance(report, dict) or not isinstance(normalized, list):
        raise ValueError("AI imported layer has an invalid structure.")

    known_refs = set(evidence_index)
    theme_count = 0
    connection_count = 0
    interpretation_rejected = 0
    validated_prospects: list[dict[str, object]] = []
    for prospect in normalized:
        if not isinstance(prospect, dict):
            continue
        copy = dict(prospect)
        themes, rejected_themes = _validated_interpretations(
            copy.pop("review_themes", None),
            known_refs=known_refs,
            kind="review_theme",
        )
        connections, rejected_connections = _validated_interpretations(
            copy.pop("evidence_connections", None),
            known_refs=known_refs,
            kind="evidence_connection",
        )
        copy["validated_review_themes"] = themes
        copy["validated_evidence_connections"] = connections
        copy["rejected_interpretations"] = rejected_themes + rejected_connections
        theme_count += len(themes)
        connection_count += len(connections)
        interpretation_rejected += len(rejected_themes) + len(rejected_connections)
        validated_prospects.append(copy)

    manifest["schema_version"] = IMPORTED_SCHEMA_VERSION
    manifest["interpretation_rule"] = (
        "review themes and evidence connections are validated only when every cited evidence ref exists"
    )
    report["review_themes_accepted"] = theme_count
    report["evidence_connections_accepted"] = connection_count
    report["interpretations_rejected"] = interpretation_rejected

    files["manifest.json"] = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    files["validation_report.json"] = json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
    files["normalized_enrichment.json"] = json.dumps(
        validated_prospects,
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
    files["README.md"] = (
        "# VERIDRA AI Imported Layer\n\n"
        "Validated read-only AI interpretation. Raw evidence, prospect state and outreach state are "
        "not mutated. A/B/C commercial claims require valid evidence refs; Level D remains "
        "analysis-only. Review themes and evidence connections appear only in their `validated_*` "
        "fields when all cited evidence refs exist in the source export.\n"
    ).encode("utf-8")
    _rewrite_zip(output, files)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-ai-evidence-exchange")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--competitive-input", type=Path)
    export_parser.add_argument("--visual-input", type=Path)
    export_parser.add_argument("--review-input", type=Path)
    export_parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    export_parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--input", type=Path)
    import_parser.add_argument("--source-export", type=Path)
    import_parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    import_parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "export":
        competitive = args.competitive_input or _latest(args.downloads, "VERIDRA_COMPETITIVE_*.zip")
        if competitive is None:
            raise FileNotFoundError("No VERIDRA competitive-context ZIP was found.")
        visual = args.visual_input or _latest(args.downloads, "VERIDRA_VISUAL_EVIDENCE_STRICT_*.zip")
        review = args.review_input or _latest(args.downloads, "VERIDRA_REVIEW_INTELLIGENCE_*.zip")
        output = export_pack(
            competitive_input=competitive,
            visual_input=visual,
            review_input=review,
            output_directory=args.output_directory,
        )
        print(
            json.dumps(
                {
                    "output": str(output),
                    "review_input": str(review) if review is not None else None,
                    "persistence": "none",
                    "outreach": "none",
                },
                indent=2,
            )
        )
        return 0

    enrichment = args.input or _latest(args.downloads, "VERIDRA_AI_ENRICHMENT_*.zip")
    source_export = args.source_export or _latest(args.downloads, "VERIDRA_AI_EXPORT_*.zip")
    if enrichment is None:
        raise FileNotFoundError("No VERIDRA AI enrichment ZIP was found.")
    if source_export is None:
        raise FileNotFoundError("No VERIDRA AI export ZIP was found.")
    output = import_pack(
        enrichment_input=enrichment,
        source_export_input=source_export,
        output_directory=args.output_directory,
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "persistence": "none",
                "raw_evidence_mutated": False,
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
