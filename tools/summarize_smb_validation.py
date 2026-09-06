from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _pct(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    return "n/a"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = json.loads(args.comparison.read_text(encoding="utf-8"))
    manifest = data.get("source_manifest", {})
    expectations = data.get("expectations", [])

    misses = [
        row
        for row in expectations
        if isinstance(row, dict)
        and row.get("kind") == "positive"
        and row.get("evaluable") is True
        and row.get("passed") is not True
        and row.get("excluded_from_current_metric") is not True
    ]
    blocked = [
        row
        for row in expectations
        if isinstance(row, dict) and row.get("blocked_by_acquisition") is True
    ]
    negative_failures = [
        row
        for row in expectations
        if isinstance(row, dict)
        and row.get("kind") == "negative"
        and row.get("evaluable") is True
        and row.get("passed") is not True
        and row.get("excluded_from_current_metric") is not True
    ]

    summary = {
        "audit_zip": data.get("audit_zip"),
        "targets": manifest.get("business_targets"),
        "audit_successes": manifest.get("audit_successes"),
        "audit_failures": manifest.get("audit_failures"),
        "historical_positive_recall": data.get("strict_positive_recall"),
        "current_positive_recall": data.get("current_positive_recall"),
        "current_positive_hits": data.get("current_positive_hits"),
        "current_positive_evaluable": data.get("current_positive_evaluable"),
        "current_negative_control_pass_rate": data.get(
            "current_negative_control_pass_rate"
        ),
        "adjudications_applied": data.get("adjudications_applied", 0),
        "current_material_misses": [row.get("expectation_id") for row in misses],
        "acquisition_blocked": [row.get("expectation_id") for row in blocked],
        "current_negative_control_failures": [
            row.get("expectation_id") for row in negative_failures
        ],
        "calibration_acceptance_candidate": (
            not misses and not negative_failures and data.get("current_positive_evaluable", 0) > 0
        ),
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print("\n=== VERIDRA SMB VALIDATION SUMMARY ===")
    print(
        f"Audits: {summary['audit_successes']}/{summary['targets']} successful; "
        f"{summary['audit_failures']} failed"
    )
    print(f"Historical frozen recall: {_pct(summary['historical_positive_recall'])}")
    print(
        "Current adjudicated recall: "
        f"{summary['current_positive_hits']}/{summary['current_positive_evaluable']} "
        f"({_pct(summary['current_positive_recall'])})"
    )
    print(
        "Current negative-control pass rate: "
        f"{_pct(summary['current_negative_control_pass_rate'])}"
    )
    print(f"Adjudications applied: {summary['adjudications_applied']}")
    print(
        "Current material misses: "
        + (", ".join(summary["current_material_misses"]) or "none")
    )
    print(
        "Acquisition-blocked expectations: "
        + (", ".join(summary["acquisition_blocked"]) or "none")
    )
    print(
        "Negative-control failures: "
        + (", ".join(summary["current_negative_control_failures"]) or "none")
    )
    print(
        "#298 acceptance candidate: "
        + ("YES" if summary["calibration_acceptance_candidate"] else "NO")
    )
    if args.output:
        print(f"Summary JSON: {args.output}")


if __name__ == "__main__":
    main()
