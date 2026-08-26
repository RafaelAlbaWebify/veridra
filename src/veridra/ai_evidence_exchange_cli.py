from __future__ import annotations

import argparse
import json
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


EXPORT_SCHEMA_VERSION = 1
ENRICHMENT_SCHEMA_VERSION = 1
_ALLOWED_LEVELS = {"A", "B", "C", "D"}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safe_name(value: str) -> str:
    clean = "".join(char if char.isalnum() else "-" for char in value).strip("-")
    return "-".join(part for part in clean.split("-") if part)[:100] or "prospect"


def _website_key(value: object) -> str:
    text = _text(value)
    if not text:
        return ""
    parsed = urlsplit(text)
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _read_json(archive: zipfile.ZipFile, name: str) -> object:
    try:
        return json.loads(archive.read(name))
    except KeyError as exc:
        raise ValueError(f"Required file is missing from ZIP: {name}") from exc


def _load_competitive(path: Path) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    with zipfile.ZipFile(path) as archive:
        manifest = _read_json(archive, "manifest.json")
        benchmark = _read_json(archive, "local_benchmark.json")
        contexts = _read_json(archive, "competitive_context.json")
    if not isinstance(manifest, dict) or not isinstance(benchmark, dict) or not isinstance(contexts, list):
        raise ValueError("Competitive context ZIP has an invalid structure.")
    rows = [item for item in contexts if isinstance(item, dict)]
    return manifest, benchmark, rows


def _load_visual(path: Path | None) -> list[dict[str, object]]:
    if path is None or not path.is_file():
        return []
    with zipfile.ZipFile(path) as archive:
        raw = _read_json(archive, "visual_evidence.json")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _visual_lookup(rows: list[dict[str, object]]) -> tuple[
    dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]
]:
    by_name: dict[str, list[dict[str, object]]] = {}
    by_website: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        evidence = row.get("evidence")
        values = [item for item in evidence if isinstance(item, dict)] if isinstance(evidence, list) else []
        if not values:
            continue
        name = _text(row.get("business_name")).casefold()
        website = _website_key(row.get("audit_url"))
        if name:
            by_name[name] = values
        if website:
            by_website[website] = values
    return by_name, by_website


def _response_contract(export_id: str) -> dict[str, object]:
    return {
        "schema_version": ENRICHMENT_SCHEMA_VERSION,
        "exchange_type": "veridra_ai_enrichment",
        "required_manifest": {
            "schema_version": ENRICHMENT_SCHEMA_VERSION,
            "exchange_type": "veridra_ai_enrichment",
            "source_export_id": export_id,
        },
        "required_file": "enrichment.json",
        "prospect_shape": {
            "business_name": "string",
            "review_themes": "optional list",
            "evidence_connections": "optional list",
            "commercial_claims": [
                {
                    "claim": "plain business-language statement",
                    "evidence_level": "A | B | C | D",
                    "evidence_refs": ["evidence id from evidence_index.json"],
                    "webify_action": "optional action Webify can plausibly perform",
                }
            ],
        },
        "rules": [
            "AI may interpret evidence but must not manufacture evidence.",
            "Every commercial claim must contain at least one evidence_refs entry.",
            "Evidence refs must exist in evidence_index.json from this export.",
            "Level A is direct factual evidence; B is multiple corroborating signals; C is a reasonable hypothesis; D is speculation.",
            "Level D claims are analysis-only and must not be used in outreach.",
            "The enrichment pack must not request or imply mutation of raw VERIDRA evidence or prospect state.",
        ],
    }


def export_pack(
    *,
    competitive_input: Path,
    visual_input: Path | None,
    output_directory: Path,
) -> Path:
    competitive_manifest, benchmark, contexts = _load_competitive(competitive_input)
    visual_rows = _load_visual(visual_input)
    visual_by_name, visual_by_website = _visual_lookup(visual_rows)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_id = f"veridra-ai-export-{stamp}"
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / f"VERIDRA_AI_EXPORT_{stamp}.zip"

    evidence_index: dict[str, dict[str, object]] = {}
    prospect_payloads: list[tuple[str, dict[str, object], list[dict[str, object]]]] = []
    for context in contexts:
        business_name = _text(context.get("business_name"))
        slug = _safe_name(business_name)
        website = _website_key(context.get("website"))
        evidence = visual_by_website.get(website) or visual_by_name.get(business_name.casefold()) or []
        normalized_evidence: list[dict[str, object]] = []
        for index, item in enumerate(evidence, start=1):
            evidence_id = f"visual:{slug}:{index}"
            copy = dict(item)
            copy["evidence_id"] = evidence_id
            normalized_evidence.append(copy)
            evidence_index[evidence_id] = {
                "business_name": business_name,
                "type": _text(item.get("issue_type")) or "visual_evidence",
                "source": visual_input.name if visual_input is not None else None,
                "what_we_noticed": _text(item.get("what_we_noticed")),
            }
        prospect_payloads.append((slug, context, normalized_evidence))

    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exchange_type": "veridra_ai_export",
        "export_id": export_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_competitive_context": competitive_input.name,
        "source_visual_evidence": visual_input.name if visual_input is not None else None,
        "prospects": len(contexts),
        "evidence_items": len(evidence_index),
        "persistence": "none",
        "outreach": "none",
        "provenance": "raw/deterministic VERIDRA evidence prepared for external AI interpretation",
    }

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr("cohort/local_benchmark.json", json.dumps(benchmark, indent=2, ensure_ascii=False))
        archive.writestr(
            "cohort/source_manifest.json",
            json.dumps(competitive_manifest, indent=2, ensure_ascii=False),
        )
        archive.writestr("evidence_index.json", json.dumps(evidence_index, indent=2, ensure_ascii=False))
        archive.writestr(
            "AI_RESPONSE_CONTRACT.json",
            json.dumps(_response_contract(export_id), indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "README.md",
            "# VERIDRA AI Evidence Export\n\n"
            "Read-only evidence pack for external AI interpretation. Raw/deterministic VERIDRA evidence remains authoritative. "
            "Return a `VERIDRA_AI_ENRICHMENT_*.zip` following `AI_RESPONSE_CONTRACT.json`. Commercial claims must cite evidence IDs from `evidence_index.json`.\n",
        )
        for slug, context, evidence in prospect_payloads:
            folder = f"prospects/{slug}"
            archive.writestr(
                f"{folder}/competitive_context.json",
                json.dumps(context, indent=2, ensure_ascii=False),
            )
            archive.writestr(
                f"{folder}/website_evidence.json",
                json.dumps(evidence, indent=2, ensure_ascii=False),
            )
    return output


def _validate_enrichment(
    enrichment_path: Path,
    source_export_path: Path,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    with zipfile.ZipFile(source_export_path) as source_archive:
        source_manifest = _read_json(source_archive, "manifest.json")
        evidence_index = _read_json(source_archive, "evidence_index.json")
    if not isinstance(source_manifest, dict) or not isinstance(evidence_index, dict):
        raise ValueError("Source AI export ZIP has an invalid structure.")
    export_id = _text(source_manifest.get("export_id"))

    with zipfile.ZipFile(enrichment_path) as archive:
        manifest = _read_json(archive, "manifest.json")
        enrichment = _read_json(archive, "enrichment.json")
    if not isinstance(manifest, dict) or not isinstance(enrichment, list):
        raise ValueError("AI enrichment ZIP has an invalid structure.")
    if manifest.get("schema_version") != ENRICHMENT_SCHEMA_VERSION:
        raise ValueError("Unsupported AI enrichment schema version.")
    if manifest.get("exchange_type") != "veridra_ai_enrichment":
        raise ValueError("ZIP is not a VERIDRA AI enrichment pack.")
    if _text(manifest.get("source_export_id")) != export_id:
        raise ValueError("AI enrichment pack does not match the selected VERIDRA AI export.")

    known_refs = set(evidence_index)
    normalized: list[dict[str, object]] = []
    accepted = 0
    suppressed = 0
    rejected = 0
    for prospect in enrichment:
        if not isinstance(prospect, dict):
            continue
        copy = dict(prospect)
        claims = prospect.get("commercial_claims")
        commercial_ready: list[dict[str, object]] = []
        analysis_only: list[dict[str, object]] = []
        rejected_claims: list[dict[str, object]] = []
        if isinstance(claims, list):
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                level = _text(claim.get("evidence_level")).upper()
                refs_raw = claim.get("evidence_refs")
                refs = [item for item in refs_raw if isinstance(item, str) and item] if isinstance(refs_raw, list) else []
                unknown_refs = [item for item in refs if item not in known_refs]
                if level not in _ALLOWED_LEVELS or not refs or unknown_refs:
                    rejected_copy = dict(claim)
                    rejected_copy["rejection_reason"] = (
                        "invalid evidence level, missing evidence refs, or unknown evidence refs"
                    )
                    rejected_claims.append(rejected_copy)
                    rejected += 1
                    continue
                if level == "D":
                    analysis_only.append(dict(claim))
                    suppressed += 1
                else:
                    commercial_ready.append(dict(claim))
                    accepted += 1
        copy["commercial_ready_claims"] = commercial_ready
        copy["analysis_only_claims"] = analysis_only
        copy["rejected_claims"] = rejected_claims
        normalized.append(copy)

    report = {
        "schema_version": 1,
        "source_export_id": export_id,
        "source_export": source_export_path.name,
        "source_enrichment": enrichment_path.name,
        "commercial_claims_accepted": accepted,
        "level_d_claims_suppressed": suppressed,
        "claims_rejected": rejected,
        "persistence": "none",
        "raw_evidence_mutated": False,
    }
    return manifest, normalized, report


def import_pack(
    *,
    enrichment_input: Path,
    source_export_input: Path,
    output_directory: Path,
) -> Path:
    enrichment_manifest, normalized, report = _validate_enrichment(
        enrichment_input,
        source_export_input,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / f"VERIDRA_AI_IMPORTED_{stamp}.zip"
    manifest = {
        "schema_version": 1,
        "exchange_type": "veridra_ai_imported_layer",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_export_id": report["source_export_id"],
        "source_export": source_export_input.name,
        "source_enrichment": enrichment_input.name,
        "persistence": "none",
        "raw_evidence_mutated": False,
        "commercial_rule": "only A/B/C claims with valid evidence refs are commercial-ready",
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr(
            "source_enrichment_manifest.json",
            json.dumps(enrichment_manifest, indent=2, ensure_ascii=False),
        )
        archive.writestr("validation_report.json", json.dumps(report, indent=2, ensure_ascii=False))
        archive.writestr("normalized_enrichment.json", json.dumps(normalized, indent=2, ensure_ascii=False))
        archive.writestr(
            "README.md",
            "# VERIDRA AI Imported Layer\n\n"
            "Validated read-only AI interpretation. This pack does not overwrite raw evidence, prospect state, or outreach state. "
            "Only A/B/C commercial claims with evidence references found in the source export are placed in `commercial_ready_claims`; Level D is analysis-only.\n",
        )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-ai-evidence-exchange")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--competitive-input", type=Path)
    export_parser.add_argument("--visual-input", type=Path)
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
        output = export_pack(
            competitive_input=competitive,
            visual_input=visual,
            output_directory=args.output_directory,
        )
        print(json.dumps({"output": str(output), "persistence": "none", "outreach": "none"}, indent=2))
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
    print(json.dumps({"output": str(output), "persistence": "none", "raw_evidence_mutated": False}, indent=2))
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
