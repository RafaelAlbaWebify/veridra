from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path


DECISION_FIELDS = (
    "validation_state",
    "owner_understandable",
    "commercially_relevant",
    "webify_remediable",
    "presence_care_class",
    "review_notes",
)


def _rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _write(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8-sig")


def _norm(value: str) -> str:
    return value.strip().casefold()


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review-directory",
        type=Path,
        default=Path("artifacts/smb-validation/human-validation"),
    )
    args = parser.parse_args(argv)

    grouped_path = args.review_directory / "grouped_finding_review.csv"
    finding_path = args.review_directory / "finding_review.csv"

    grouped_fields, grouped = _rows(grouped_path)
    finding_fields, findings = _rows(finding_path)
    del grouped_fields

    applied_groups = 0
    applied_rows = 0

    for group in grouped:
        if _norm(group.get("apply_to_all_covered_rows", "")) != "yes":
            continue

        business = group.get("business_name", "")
        finding_id = group.get("finding_id", "")
        severity = group.get("severity", "")
        expected_count = int(group.get("covered_finding_rows", "0") or 0)

        matched = [
            row
            for row in findings
            if row.get("business_name", "") == business
            and row.get("finding_id", "") == finding_id
            and row.get("severity", "") == severity
        ]

        if len(matched) != expected_count:
            raise ValueError(
                f"Group {group.get('group_index')} expected {expected_count} rows "
                f"but matched {len(matched)}"
            )

        for row in matched:
            for field in DECISION_FIELDS:
                row[field] = group.get(field, "")
        applied_groups += 1
        applied_rows += len(matched)

    _write(finding_path, finding_fields, findings)

    print(
        f"[Veridra] Applied {applied_groups} grouped decisions "
        f"to {applied_rows} raw finding rows."
    )
    print(
        "[Veridra] Groups without apply_to_all_covered_rows=yes were left untouched."
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
