from __future__ import annotations

import csv
import importlib.util
import json
import zipfile
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[1] / "tools" / "build_smb_validation_input.py"
    spec = importlib.util.spec_from_file_location("build_smb_validation_input", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "business_name",
        "website",
        "locality",
        "county_or_region",
        "sector",
        "apparent_smb_fit",
        "provenance_url",
        "review_date",
        "no_contact",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_build_archive_preserves_no_contact_and_existing_audit_shape(tmp_path: Path) -> None:
    tool = _tool()
    source = tmp_path / "cohort.csv"
    output = tmp_path / "validation.zip"
    _write_csv(
        source,
        [
            {
                "business_name": "Example Dental",
                "website": "https://example.com/",
                "locality": "Dublin",
                "county_or_region": "Dublin",
                "sector": "Dental practice",
                "apparent_smb_fit": "likely",
                "provenance_url": "https://example.com/about",
                "review_date": "2026-09-05",
                "no_contact": "true",
            }
        ],
    )

    count = tool.build_archive(source, output)

    assert count == 1
    with zipfile.ZipFile(output) as archive:
        observations = json.loads(archive.read("captured_observations.json"))
        manifest = json.loads(archive.read("manifest.json"))
        readme = archive.read("README.md").decode("utf-8")
    assert observations[0]["result_rank"] == 1
    assert observations[0]["business"]["name"] == "Example Dental"
    assert observations[0]["business"]["website"] == "https://example.com/"
    assert observations[0]["business"]["source_url"] == "https://example.com/about"
    assert observations[0]["validation_context"]["no_contact"] is True
    assert manifest["no_contact"] is True
    assert manifest["persistence"] == "none"
    assert "does not authorize outreach" in readme


def test_adapter_rejects_any_row_not_explicitly_no_contact(tmp_path: Path) -> None:
    tool = _tool()
    source = tmp_path / "cohort.csv"
    _write_csv(
        source,
        [
            {
                "business_name": "Unsafe Dental",
                "website": "https://example.com/",
                "locality": "Dublin",
                "county_or_region": "Dublin",
                "sector": "Dental practice",
                "apparent_smb_fit": "likely",
                "provenance_url": "https://example.com/",
                "review_date": "2026-09-05",
                "no_contact": "false",
            }
        ],
    )

    with pytest.raises(ValueError, match="no_contact must be true"):
        tool.build_archive(source, tmp_path / "validation.zip")


def test_adapter_deduplicates_identical_websites(tmp_path: Path) -> None:
    tool = _tool()
    source = tmp_path / "cohort.csv"
    row = {
        "business_name": "Example Dental",
        "website": "https://example.com/",
        "locality": "Dublin",
        "county_or_region": "Dublin",
        "sector": "Dental practice",
        "apparent_smb_fit": "likely",
        "provenance_url": "https://example.com/",
        "review_date": "2026-09-05",
        "no_contact": "true",
    }
    _write_csv(source, [row, row])

    count = tool.build_archive(source, tmp_path / "validation.zip")

    assert count == 1
