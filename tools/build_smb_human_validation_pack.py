from __future__ import annotations

import argparse  # noqa: I001
import csv
import io
import json
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ANCHORS = (
    "Dublin City Dentist",
    "Crown Dental Dublin",
    "MB Dental",
    "G-Dental",
)


def _latest_audit_zip(outdir: Path) -> Path:
    values = sorted(
        outdir.glob("VERIDRA_PROSPECT_AUDITS_*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not values:
        raise FileNotFoundError(f"No VERIDRA_PROSPECT_AUDITS_*.zip found in {outdir}")
    return values[0]


def _cohort_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row.get("business_name", "")).strip(): dict(row)
            for row in csv.DictReader(handle)
            if str(row.get("business_name", "")).strip()
        }


def _assessments(archive: zipfile.ZipFile) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for member in archive.namelist():
        if not member.startswith("assessments/") or not member.endswith(".json"):
            continue
        filename = member.rsplit("/", 1)[-1]
        try:
            rank = int(filename.split("-", 1)[0])
        except ValueError:
            continue
        result[rank] = json.loads(archive.read(member))
    return result


def _diversity_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            int(row.get("technical_finding_weight", 0)),
            int(row.get("result_rank", 0)),
        ),
    )
    result: list[dict[str, Any]] = []
    low = 0
    high = len(ordered) - 1
    take_high = True
    while low <= high:
        if take_high:
            result.append(ordered[high])
            high -= 1
        else:
            result.append(ordered[low])
            low += 1
        take_high = not take_high
    return result


def _select(
    ranking: list[dict[str, Any]],
    cohort: dict[str, dict[str, str]],
    count: int,
) -> list[dict[str, Any]]:
    successful = [
        row
        for row in ranking
        if isinstance(row, dict) and row.get("audit_status") == "success"
    ]
    by_name = {str(row.get("name", "")): row for row in successful}

    selected: list[dict[str, Any]] = []
    selected_names: set[str] = set()
    for name in ANCHORS:
        row = by_name.get(name)
        if row is not None and name not in selected_names:
            selected.append(row)
            selected_names.add(name)

    remaining = [
        row for row in successful if str(row.get("name", "")) not in selected_names
    ]
    locality_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in remaining:
        name = str(row.get("name", ""))
        locality = cohort.get(name, {}).get("locality", "") or "Unknown"
        locality_buckets[locality].append(row)

    for locality in list(locality_buckets):
        locality_buckets[locality] = _diversity_order(locality_buckets[locality])

    locality_order = sorted(locality_buckets)
    cursor = 0
    while len(selected) < count and locality_order:
        locality = locality_order[cursor % len(locality_order)]
        bucket = locality_buckets[locality]
        if bucket:
            row = bucket.pop(0)
            name = str(row.get("name", ""))
            if name not in selected_names:
                selected.append(row)
                selected_names.add(name)
        locality_order = [value for value in locality_order if locality_buckets[value]]
        cursor += 1

    return selected[:count]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8-sig")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-zip", type=Path)
    parser.add_argument(
        "--cohort",
        type=Path,
        default=Path("evidence/smb-validation/ie-dental-cohort-v1.csv"),
    )
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("artifacts/smb-validation/human-validation"),
    )
    args = parser.parse_args(argv)

    if not 10 <= args.count <= 15:
        raise ValueError("--count must be between 10 and 15")

    audit_zip = args.audit_zip or _latest_audit_zip(Path("artifacts/smb-validation"))
    cohort = _cohort_rows(args.cohort)

    with zipfile.ZipFile(audit_zip) as archive:
        ranking = json.loads(archive.read("audit_ranking.json"))
        if not isinstance(ranking, list):
            raise ValueError("audit_ranking.json must contain a list")
        assessments = _assessments(archive)

    selected = _select(ranking, cohort, args.count)
    args.output_directory.mkdir(parents=True, exist_ok=True)

    business_rows: list[dict[str, Any]] = []
    finding_rows: list[dict[str, Any]] = []
    grouped_review_rows: list[dict[str, Any]] = []
    family_review_rows: list[dict[str, Any]] = []

    for selection_order, row in enumerate(selected, start=1):
        name = str(row.get("name", ""))
        rank = int(row.get("result_rank", 0))
        meta = cohort.get(name, {})
        assessment = assessments.get(rank, {})
        findings = assessment.get("findings", [])
        attention = [
            item
            for item in findings
            if isinstance(item, dict) and item.get("status") == "attention"
        ]

        business_rows.append(
            {
                "selection_order": selection_order,
                "business_name": name,
                "locality": meta.get("locality", ""),
                "county_or_region": meta.get("county_or_region", ""),
                "audit_url": row.get("audit_url", ""),
                "technical_finding_weight": row.get("technical_finding_weight", 0),
                "attention_findings": len(attention),
                "operator_validation_minutes": "",
                "material_human_miss_count": "",
                "material_human_miss_notes": "",
                "business_review_complete": "",
            }
        )

        for finding_index, finding in enumerate(attention, start=1):
            finding_rows.append(
                {
                    "selection_order": selection_order,
                    "business_name": name,
                    "finding_index": finding_index,
                    "finding_id": finding.get("id", ""),
                    "area": finding.get("area", ""),
                    "severity": finding.get("severity", ""),
                    "title": finding.get("title", ""),
                    "summary": finding.get("summary", ""),
                    "recommendation": finding.get("recommendation", ""),
                    "evidence_json": json.dumps(
                        finding.get("evidence", {}),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "validation_state": "",
                    "owner_understandable": "",
                    "commercially_relevant": "",
                    "webify_remediable": "",
                    "presence_care_class": "",
                    "review_notes": "",
                }
            )

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in finding_rows:
        key = (
            str(row["business_name"]),
            str(row["finding_id"]),
            str(row["severity"]),
        )
        grouped[key].append(row)

    for group_index, key in enumerate(sorted(grouped), start=1):
        rows = grouped[key]
        representative = rows[0]
        grouped_review_rows.append(
            {
                "group_index": group_index,
                "business_name": representative["business_name"],
                "finding_id": representative["finding_id"],
                "severity": representative["severity"],
                "area": representative["area"],
                "title": representative["title"],
                "representative_summary": representative["summary"],
                "representative_recommendation": representative["recommendation"],
                "representative_evidence_json": representative["evidence_json"],
                "covered_finding_rows": len(rows),
                "covered_finding_indices": ",".join(
                    str(item["finding_index"]) for item in rows
                ),
                "validation_state": "",
                "owner_understandable": "",
                "commercially_relevant": "",
                "webify_remediable": "",
                "presence_care_class": "",
                "apply_to_all_covered_rows": "",
                "review_notes": "",
            }
        )

    family_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in finding_rows:
        key = (
            str(row["finding_id"]),
            str(row["severity"]),
        )
        family_groups[key].append(row)

    for family_index, key in enumerate(sorted(family_groups), start=1):
        rows = family_groups[key]
        representative = rows[0]
        occurrence_bundle = [
            {
                "business_name": item["business_name"],
                "finding_index": item["finding_index"],
                "summary": item["summary"],
                "recommendation": item["recommendation"],
                "evidence": json.loads(str(item["evidence_json"])),
            }
            for item in rows
        ]
        family_review_rows.append(
            {
                "family_index": family_index,
                "finding_id": representative["finding_id"],
                "severity": representative["severity"],
                "area": representative["area"],
                "title": representative["title"],
                "occurrence_count": len(rows),
                "business_count": len({str(item["business_name"]) for item in rows}),
                "occurrences_json": json.dumps(
                    occurrence_bundle,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "validation_state": "",
                "owner_understandable": "",
                "commercially_relevant": "",
                "webify_remediable": "",
                "presence_care_class": "",
                "apply_to_all_occurrences": "",
                "review_notes": "",
            }
        )

    business_fields = [
        "selection_order",
        "business_name",
        "locality",
        "county_or_region",
        "audit_url",
        "technical_finding_weight",
        "attention_findings",
        "operator_validation_minutes",
        "material_human_miss_count",
        "material_human_miss_notes",
        "business_review_complete",
    ]
    finding_fields = [
        "selection_order",
        "business_name",
        "finding_index",
        "finding_id",
        "area",
        "severity",
        "title",
        "summary",
        "recommendation",
        "evidence_json",
        "validation_state",
        "owner_understandable",
        "commercially_relevant",
        "webify_remediable",
        "presence_care_class",
        "review_notes",
    ]

    grouped_review_fields = [
        "group_index",
        "business_name",
        "finding_id",
        "severity",
        "area",
        "title",
        "representative_summary",
        "representative_recommendation",
        "representative_evidence_json",
        "covered_finding_rows",
        "covered_finding_indices",
        "validation_state",
        "owner_understandable",
        "commercially_relevant",
        "webify_remediable",
        "presence_care_class",
        "apply_to_all_covered_rows",
        "review_notes",
    ]

    family_review_fields = [
        "family_index",
        "finding_id",
        "severity",
        "area",
        "title",
        "occurrence_count",
        "business_count",
        "occurrences_json",
        "validation_state",
        "owner_understandable",
        "commercially_relevant",
        "webify_remediable",
        "presence_care_class",
        "apply_to_all_occurrences",
        "review_notes",
    ]

    _write_csv(args.output_directory / "business_review.csv", business_fields, business_rows)
    _write_csv(args.output_directory / "finding_review.csv", finding_fields, finding_rows)
    _write_csv(
        args.output_directory / "grouped_finding_review.csv",
        grouped_review_fields,
        grouped_review_rows,
    )
    _write_csv(
        args.output_directory / "family_finding_review.csv",
        family_review_fields,
        family_review_rows,
    )

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_audit_zip": audit_zip.name,
        "source_cohort": args.cohort.as_posix(),
        "selected_businesses": len(business_rows),
        "attention_findings_to_review": len(finding_rows),
        "grouped_review_rows": len(grouped_review_rows),
        "family_review_rows": len(family_review_rows),
        "anchors_requested": list(ANCHORS),
        "selection_method": (
            "successful audits; include available calibration anchors; then locality-balanced "
            "round-robin with alternating high/low technical finding weight"
        ),
        "safety_boundary": (
            "public evidence review only; no outreach, forms, auth or modification"
        ),
    }
    (args.output_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.output_directory / "README.md").write_text(
        "# VERIDRA SMB human-validation pack\n\n"
        "Start with family_finding_review.csv. It groups the same finding ID and "
        "severity across all selected businesses and embeds every occurrence/evidence "
        "item in occurrences_json. If all occurrences support one judgment, set "
        "apply_to_all_occurrences=yes. Use grouped_finding_review.csv as the narrower "
        "per-business fallback, and finding_review.csv for individual exceptions. "
        "For each row fill validation_state = true/false/unverified; "
        "owner_understandable, commercially_relevant, webify_remediable = yes/no; "
        "presence_care_class = activation/monthly allowance/separate quote/monitor-only/"
        "informational/discard; and optional review_notes.\n\n"
        "For each business fill operator_validation_minutes, any material human-discovered "
        "misses, and set business_review_complete=yes only when its review is complete.\n\n"
        "Do not contact businesses, submit forms, authenticate or modify systems.\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "audit_zip": str(audit_zip),
                "output_directory": str(args.output_directory),
                "selected_businesses": len(business_rows),
                "attention_findings_to_review": len(finding_rows),
                "grouped_review_rows": len(grouped_review_rows),
                "family_review_rows": len(family_review_rows),
                "selected_names": [row["business_name"] for row in business_rows],
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
