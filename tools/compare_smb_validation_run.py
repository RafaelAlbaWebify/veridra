from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


def _norm_url(value: str) -> str:
    return value.rstrip("/").casefold()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _assessment_by_business(archive: zipfile.ZipFile) -> dict[str, dict[str, Any]]:
    ranking = json.loads(archive.read("audit_ranking.json"))
    rank_to_name = {
        int(row["result_rank"]): str(row["name"])
        for row in ranking
        if isinstance(row, dict)
        and row.get("audit_status") == "success"
        and isinstance(row.get("result_rank"), int)
    }
    result: dict[str, dict[str, Any]] = {}
    for member in archive.namelist():
        if not member.startswith("assessments/") or not member.endswith(".json"):
            continue
        filename = member.rsplit("/", 1)[-1]
        try:
            rank = int(filename.split("-", 1)[0])
        except ValueError:
            continue
        name = rank_to_name.get(rank)
        if name is None:
            continue
        result[name] = json.loads(archive.read(member))
    return result


def _finding(assessment: dict[str, Any], finding_id: str) -> dict[str, Any] | None:
    findings = assessment.get("findings", [])
    if not isinstance(findings, list):
        return None
    for item in findings:
        if isinstance(item, dict) and item.get("id") == finding_id:
            return item
    return None


def _evidence_items(finding: dict[str, Any], collection: str) -> list[dict[str, Any]]:
    evidence = finding.get("evidence", {})
    if not isinstance(evidence, dict):
        return []
    values = evidence.get(collection, [])
    return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def _item_has_url(item: dict[str, Any], expected: str) -> bool:
    expected_norm = _norm_url(expected)
    for key in ("url", "first_url", "second_url"):
        value = item.get(key)
        if isinstance(value, str) and _norm_url(value) == expected_norm:
            return True
    return False


def _matches_positive(expectation: dict[str, Any], finding: dict[str, Any] | None) -> bool:
    if finding is None or finding.get("status") != "attention":
        return False
    collection = expectation.get("evidence_collection")
    if not isinstance(collection, str):
        return True
    items = _evidence_items(finding, collection)
    expected_url = expectation.get("evidence_url")
    expected_pattern = expectation.get("evidence_pattern")
    expected_text = expectation.get("evidence_text_contains")
    for item in items:
        if isinstance(expected_url, str) and not _item_has_url(item, expected_url):
            continue
        if isinstance(expected_pattern, str) and item.get("pattern") != expected_pattern:
            continue
        if isinstance(expected_text, str):
            haystack = json.dumps(item, ensure_ascii=False).casefold()
            if expected_text.casefold() not in haystack:
                continue
        return True
    return False


def compare(audit_zip: Path, expectations_path: Path) -> dict[str, Any]:
    expectations_doc = _load_json(expectations_path)
    expectations = expectations_doc.get("expectations", [])
    if not isinstance(expectations, list):
        raise ValueError("expectations must be a list")

    with zipfile.ZipFile(audit_zip) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        ranking = json.loads(archive.read("audit_ranking.json"))
        assessments = _assessment_by_business(archive)

    rows: list[dict[str, Any]] = []
    positive_evaluable = 0
    positive_hits = 0
    negative_evaluable = 0
    negative_passes = 0

    failed_names = {
        str(row.get("name"))
        for row in ranking
        if isinstance(row, dict) and row.get("audit_status") == "failed"
    }

    for raw in expectations:
        if not isinstance(raw, dict):
            continue
        business = str(raw.get("business_name", ""))
        kind = str(raw.get("kind", "positive"))
        assessment = assessments.get(business)
        blocked = assessment is None and business in failed_names
        finding = _finding(assessment, str(raw.get("finding_id", ""))) if assessment else None

        if kind == "negative":
            evaluable = assessment is not None
            passed = bool(evaluable and (finding is None or finding.get("status") != "attention"))
            if evaluable:
                negative_evaluable += 1
                negative_passes += int(passed)
        else:
            evaluable = assessment is not None
            passed = bool(evaluable and _matches_positive(raw, finding))
            if evaluable:
                positive_evaluable += 1
                positive_hits += int(passed)

        rows.append(
            {
                "expectation_id": raw.get("id"),
                "business_name": business,
                "kind": kind,
                "finding_id": raw.get("finding_id"),
                "evaluable": evaluable,
                "blocked_by_acquisition": blocked,
                "passed": passed,
            }
        )

    return {
        "schema_version": 1,
        "audit_zip": audit_zip.name,
        "source_manifest": manifest,
        "positive_evaluable": positive_evaluable,
        "positive_hits": positive_hits,
        "strict_positive_recall": (
            positive_hits / positive_evaluable if positive_evaluable else None
        ),
        "negative_evaluable": negative_evaluable,
        "negative_passes": negative_passes,
        "negative_control_pass_rate": (
            negative_passes / negative_evaluable if negative_evaluable else None
        ),
        "expectations": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-zip", type=Path, required=True)
    parser.add_argument(
        "--expectations",
        type=Path,
        default=Path("evidence/smb-validation/ie-dental-seed-expectations-v1.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = compare(args.audit_zip, args.expectations)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
