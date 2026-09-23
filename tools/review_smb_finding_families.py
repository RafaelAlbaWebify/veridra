from __future__ import annotations

import argparse  # noqa: I001
import csv
import json
from pathlib import Path


VALID_STATES = {"true", "false", "unverified", "skip"}
YES_NO = {"yes", "no", "skip"}
VALID_CLASSES = {
    "activation",
    "monthly allowance",
    "separate quote",
    "monitor-only",
    "informational",
    "discard",
    "skip",
}


def _rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _write(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _ask(label: str, allowed: set[str]) -> str:
    choices = sorted(allowed | {"q", "exit"})
    while True:
        try:
            value = input(f"{label} [{'/'.join(choices)}]: ").strip().casefold()
        except (KeyboardInterrupt, EOFError):
            print("\n[Veridra] Review stopped cleanly. Completed decisions remain saved.")
            raise SystemExit(0) from None
        if value in {"q", "exit"}:
            print("[Veridra] Review stopped cleanly. Completed decisions remain saved.")
            raise SystemExit(0)
        if value in allowed:
            return value
        print("Invalid value.")


def _suggested_policy(finding_id: str, severity: str) -> dict[str, str]:
    finding_id = finding_id.casefold()
    severity = severity.casefold()
    owner = "yes"
    commercial = "yes" if severity in {"high", "critical"} else "no"
    remediable = "yes"
    service_class = "activation" if severity in {"high", "critical"} else "monthly allowance"

    if finding_id.startswith("accessibility."):
        commercial = "yes" if severity == "high" else "no"
        service_class = "activation" if severity == "high" else "monthly allowance"
    if "copyright" in finding_id or "explicit-update-age" in finding_id:
        commercial = "no"
        service_class = "monitor-only"
    if "opening-hours" in finding_id or "placeholder-default" in finding_id:
        commercial = "yes"
        service_class = "activation"
    if "security" in finding_id and severity in {"low", "medium"}:
        service_class = "monitor-only"

    return {
        "owner_understandable": owner,
        "commercially_relevant": commercial,
        "webify_remediable": remediable,
        "presence_care_class": service_class,
    }


def _preview_occurrences(raw: str, limit: int = 4) -> None:
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        print("Evidence preview unavailable.")
        return
    if not isinstance(values, list):
        print("Evidence preview unavailable.")
        return
    print(f"Occurrences in family: {len(values)}")
    for item in values[:limit]:
        if not isinstance(item, dict):
            continue
        business = item.get("business_name", "")
        summary = item.get("summary", "")
        evidence = item.get("evidence", {})
        compact = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        if len(compact) > 700:
            compact = compact[:697] + "..."
        print(f"- {business}: {summary}")
        print(f"  evidence: {compact}")
    if len(values) > limit:
        print(f"... plus {len(values) - limit} more occurrence(s) in this family.")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review-directory",
        type=Path,
        default=Path("artifacts/smb-validation/human-validation"),
    )
    args = parser.parse_args(argv)

    path = args.review_directory / "family_finding_review.csv"
    fields, rows = _rows(path)

    independent_path = args.review_directory / "independent_technical_verification.csv"
    independent_by_family: dict[str, dict[str, str]] = {}
    if independent_path.exists():
        _, independent_rows = _rows(independent_path)
        independent_by_family = {
            row.get("family_index", ""): row
            for row in independent_rows
            if row.get("family_index", "")
        }

    pending = [
        index
        for index, row in enumerate(rows)
        if row.get("apply_to_all_occurrences", "").strip().casefold() != "yes"
    ]

    print(f"[Veridra] Family review: {len(rows)} total, {len(pending)} pending.")
    print("[Veridra] Commands are written immediately after each completed family.")
    print("[Veridra] Use 'skip' whenever one family cannot be judged uniformly.")

    for ordinal, row_index in enumerate(pending, start=1):
        row = rows[row_index]
        print("\n" + "=" * 78)
        print(
            f"Family {row.get('family_index')} | pending {ordinal}/{len(pending)} | "
            f"{row.get('finding_id')} | severity={row.get('severity')}"
        )
        print(
            f"Businesses: {row.get('business_count')} | "
            f"Occurrences: {row.get('occurrence_count')}"
        )
        print(f"Area: {row.get('area')}")
        print(f"Title: {row.get('title')}")
        _preview_occurrences(row.get("occurrences_json", ""))

        independent = independent_by_family.get(row.get("family_index", ""))
        if independent:
            print(
                "Independent technical cross-check: "
                f"{independent.get('independent_state')} | "
                f"confirmed={independent.get('urls_confirmed')} | "
                f"contradicted={independent.get('urls_contradicted')} | "
                f"inconclusive={independent.get('urls_inconclusive')}"
            )
        else:
            print("Independent technical cross-check: not available for this family")
        suggested = _suggested_policy(
            row.get("finding_id", ""),
            row.get("severity", ""),
        )
        print("Suggested service/commercial classification (NOT a truth validation):")
        print(
            "  owner_understandable={owner_understandable}, "
            "commercially_relevant={commercially_relevant}, "
            "webify_remediable={webify_remediable}, "
            "presence_care_class={presence_care_class}".format(**suggested)
        )
        print(
            "Validate truth only if the displayed evidence is sufficient; otherwise use skip."
        )

        state = _ask("validation_state", VALID_STATES)
        if state == "skip":
            print("[Veridra] Skipped; use per-business/individual review for this family.")
            continue

        owner = _ask("owner_understandable", YES_NO)
        commercial = _ask("commercially_relevant", YES_NO)
        remediable = _ask("webify_remediable", YES_NO)
        service_class = _ask("presence_care_class", VALID_CLASSES)

        if "skip" in {owner, commercial, remediable, service_class}:
            print("[Veridra] Skipped; no bulk decision written.")
            continue

        notes = input("review_notes [optional]: ").strip()
        confirm = input("Apply this judgment to ALL occurrences? [yes/no]: ").strip().casefold()
        if confirm != "yes":
            print("[Veridra] Not applied; family remains pending.")
            continue

        row["validation_state"] = state
        row["owner_understandable"] = owner
        row["commercially_relevant"] = commercial
        row["webify_remediable"] = remediable
        row["presence_care_class"] = service_class
        row["apply_to_all_occurrences"] = "yes"
        row["review_notes"] = notes
        _write(path, fields, rows)
        print("[Veridra] Saved.")

    remaining = sum(
        row.get("apply_to_all_occurrences", "").strip().casefold() != "yes"
        for row in rows
    )
    print(f"\n[Veridra] Guided family review finished. Remaining families: {remaining}.")
    print(
        "[Veridra] Run VERIDRA_SMB_HUMAN_VALIDATION.bat apply "
        "to propagate approved family decisions."
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
