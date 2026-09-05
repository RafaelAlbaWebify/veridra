from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a controlled no-contact SMB validation CSV into the discovery ZIP shape "
            "accepted by veridra-prospect-audit-evidence."
        )
    )
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_zip", type=Path)
    return parser


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "y"}


def _validate_public_http_url(value: str, *, field: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTP(S) URL: {value!r}")
    return value.strip()


def _provider_key(name: str, website: str) -> str:
    digest = hashlib.sha256(f"{name}\n{website}".encode("utf-8")).hexdigest()[:16]
    return f"smb-validation-{digest}"


def convert_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    seen_websites: set[str] = set()
    for index, row in enumerate(rows, start=1):
        name = row.get("business_name", "").strip()
        website = _validate_public_http_url(row.get("website", ""), field="website")
        provenance = _validate_public_http_url(
            row.get("provenance_url", ""), field="provenance_url"
        )
        if not name:
            raise ValueError(f"Row {index}: business_name is required.")
        if not _truthy(row.get("no_contact", "")):
            raise ValueError(
                f"Row {index}: no_contact must be true for SMB validation input."
            )
        normalized = website.rstrip("/").casefold()
        if normalized in seen_websites:
            continue
        seen_websites.add(normalized)
        observations.append(
            {
                "result_rank": len(observations) + 1,
                "business": {
                    "name": name,
                    "website": website,
                    "provider_key": _provider_key(name, website),
                    "source_url": provenance,
                },
                "validation_context": {
                    "market": "Ireland",
                    "purpose": "real-SMB digital-presence validation",
                    "no_contact": True,
                    "apparent_smb_fit": row.get("apparent_smb_fit", "").strip(),
                    "locality": row.get("locality", "").strip(),
                    "region": row.get("county_or_region", "").strip(),
                    "sector": row.get("sector", "").strip(),
                    "review_date": row.get("review_date", "").strip(),
                },
            }
        )
    if not observations:
        raise ValueError("No valid SMB validation rows were found.")
    return observations


def build_archive(input_csv: Path, output_zip: Path) -> int:
    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    observations = convert_rows(rows)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "purpose": "real-SMB digital-presence validation",
        "source_csv": input_csv.name,
        "business_targets": len(observations),
        "no_contact": True,
        "persistence": "none",
        "next_command": (
            "veridra-prospect-audit-evidence --input <this-zip> "
            f"--max-targets {len(observations)}"
        ),
    }
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "captured_observations.json",
            json.dumps(observations, indent=2, ensure_ascii=False).encode("utf-8"),
        )
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
        )
        archive.writestr(
            "README.md",
            (
                "# VERIDRA real-SMB validation input\n\n"
                "This archive is a no-contact adapter from the controlled CSV cohort to the "
                "existing read-only prospect audit evidence CLI. It does not authorize outreach, "
                "form submission, authentication or changes to any sampled business.\n"
            ).encode("utf-8"),
        )
    return len(observations)


def main() -> None:
    args = build_parser().parse_args()
    count = build_archive(args.input_csv, args.output_zip)
    print(
        json.dumps(
            {
                "input": str(args.input_csv),
                "output": str(args.output_zip),
                "business_targets": count,
                "no_contact": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
