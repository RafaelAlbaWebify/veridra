from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any


VALID_STATES = {"true", "false", "unverified"}
YES_NO = {"yes", "no"}
VALID_CLASSES = {
    "activation",
    "monthly allowance",
    "separate quote",
    "monitor-only",
    "informational",
    "discard",
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _norm(value: str) -> str:
    return value.strip().casefold()


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review-directory",
        type=Path,
        default=Path("artifacts/smb-validation/human-validation"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    finding_rows = _rows(args.review_directory / "finding_review.csv")
    business_rows = _rows(args.review_directory / "business_review.csv")

    finding_errors: list[str] = []
    reviewed: list[dict[str, str]] = []

    for index, row in enumerate(finding_rows, start=2):
        state = _norm(row.get("validation_state", ""))
        owner = _norm(row.get("owner_understandable", ""))
        commercial = _norm(row.get("commercially_relevant", ""))
        remediable = _norm(row.get("webify_remediable", ""))
        service_class = _norm(row.get("presence_care_class", ""))

        if not state:
            continue
        if state not in VALID_STATES:
            finding_errors.append(f"finding_review.csv row {index}: invalid validation_state")
            continue
        if owner not in YES_NO:
            finding_errors.append(f"finding_review.csv row {index}: owner_understandable required")
            continue
        if commercial not in YES_NO:
            finding_errors.append(f"finding_review.csv row {index}: commercially_relevant required")
            continue
        if remediable not in YES_NO:
            finding_errors.append(f"finding_review.csv row {index}: webify_remediable required")
            continue
        if service_class not in VALID_CLASSES:
            finding_errors.append(f"finding_review.csv row {index}: invalid presence_care_class")
            continue
        reviewed.append(row)

    completed_businesses: list[dict[str, str]] = []
    business_errors: list[str] = []
    validation_minutes: list[float] = []
    material_misses = 0

    for index, row in enumerate(business_rows, start=2):
        if _norm(row.get("business_review_complete", "")) != "yes":
            continue
        try:
            minutes = float(row.get("operator_validation_minutes", ""))
            misses = int(row.get("material_human_miss_count", ""))
        except ValueError:
            business_errors.append(
                f"business_review.csv row {index}: minutes and material miss count are required"
            )
            continue
        if minutes < 0 or misses < 0:
            business_errors.append(
                f"business_review.csv row {index}: values must be non-negative"
            )
            continue
        completed_businesses.append(row)
        validation_minutes.append(minutes)
        material_misses += misses

    true_count = sum(_norm(row["validation_state"]) == "true" for row in reviewed)
    false_count = sum(_norm(row["validation_state"]) == "false" for row in reviewed)
    unverified_count = sum(
        _norm(row["validation_state"]) == "unverified" for row in reviewed
    )
    truth_denominator = true_count + false_count

    owner_yes = sum(_norm(row["owner_understandable"]) == "yes" for row in reviewed)
    commercial_yes = sum(
        _norm(row["commercially_relevant"]) == "yes" for row in reviewed
    )
    remediable_yes = sum(_norm(row["webify_remediable"]) == "yes" for row in reviewed)

    credible_businesses = {
        row["business_name"]
        for row in reviewed
        if _norm(row["validation_state"]) == "true"
        and _norm(row["commercially_relevant"]) == "yes"
        and _norm(row["presence_care_class"])
        in {"activation", "monthly allowance", "separate quote", "monitor-only"}
    }

    summary: dict[str, Any] = {
        "finding_rows_total": len(finding_rows),
        "finding_rows_reviewed": len(reviewed),
        "finding_rows_remaining": len(finding_rows) - len(reviewed),
        "businesses_selected": len(business_rows),
        "businesses_complete": len(completed_businesses),
        "businesses_remaining": len(business_rows) - len(completed_businesses),
        "true_findings": true_count,
        "false_findings": false_count,
        "unverified_findings": unverified_count,
        "true_positive_rate": _rate(true_count, truth_denominator),
        "false_positive_rate": _rate(false_count, truth_denominator),
        "owner_understandable_rate": _rate(owner_yes, len(reviewed)),
        "commercially_relevant_rate": _rate(commercial_yes, len(reviewed)),
        "webify_remediable_rate": _rate(remediable_yes, len(reviewed)),
        "material_human_misses": material_misses,
        "businesses_with_credible_value_opportunity": len(credible_businesses),
        "credible_value_business_rate": _rate(
            len(credible_businesses), len(completed_businesses)
        ),
        "median_operator_validation_minutes": (
            median(validation_minutes) if validation_minutes else None
        ),
        "finding_validation_errors": finding_errors,
        "business_validation_errors": business_errors,
        "phase_c_complete": (
            10 <= len(completed_businesses) <= 15
            and len(reviewed) == len(finding_rows)
            and not finding_errors
            and not business_errors
        ),
    }

    output = args.output or args.review_directory / "HUMAN_VALIDATION_SUMMARY.json"
    output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not finding_errors and not business_errors else 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
