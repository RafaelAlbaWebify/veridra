import json
import zipfile
from pathlib import Path

import pytest

from veridra.ai_evidence_exchange_cli import export_pack, import_pack


def _write_zip(path: Path, files: dict[str, object]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            if isinstance(value, bytes):
                archive.writestr(name, value)
            else:
                archive.writestr(name, json.dumps(value))


def test_export_builds_traceable_ai_pack(tmp_path: Path) -> None:
    competitive = tmp_path / "VERIDRA_COMPETITIVE_TEST.zip"
    visual = tmp_path / "VERIDRA_VISUAL_EVIDENCE_STRICT_TEST.zip"
    _write_zip(
        competitive,
        {
            "manifest.json": {"schema_version": 3},
            "local_benchmark.json": {"business_count": 1, "rating_median": 4.8},
            "competitive_context.json": [
                {
                    "business_name": "Phoenix Dental",
                    "website": "https://phoenixdental.ie/",
                    "signals": {"rating": None},
                }
            ],
        },
    )
    _write_zip(
        visual,
        {
            "visual_evidence.json": [
                {
                    "business_name": "Phoenix Dental",
                    "audit_url": "https://phoenixdental.ie/",
                    "evidence": [
                        {
                            "issue_type": "broken_link",
                            "what_we_noticed": "The Privacy Policy link reaches a 404 page.",
                        }
                    ],
                }
            ]
        },
    )

    output = export_pack(
        competitive_input=competitive,
        visual_input=visual,
        output_directory=tmp_path,
    )

    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        evidence_index = json.loads(archive.read("evidence_index.json"))
        contract = json.loads(archive.read("AI_RESPONSE_CONTRACT.json"))
        evidence = json.loads(
            archive.read("prospects/Phoenix-Dental/website_evidence.json")
        )

    assert manifest["exchange_type"] == "veridra_ai_export"
    assert manifest["persistence"] == "none"
    assert manifest["evidence_items"] == 1
    assert "visual:Phoenix-Dental:1" in evidence_index
    assert evidence[0]["evidence_id"] == "visual:Phoenix-Dental:1"
    assert contract["required_manifest"]["source_export_id"] == manifest["export_id"]


def test_import_accepts_supported_claims_and_suppresses_level_d(tmp_path: Path) -> None:
    source_export = tmp_path / "VERIDRA_AI_EXPORT_TEST.zip"
    _write_zip(
        source_export,
        {
            "manifest.json": {
                "schema_version": 1,
                "exchange_type": "veridra_ai_export",
                "export_id": "export-1",
            },
            "evidence_index.json": {
                "visual:Phoenix-Dental:1": {
                    "business_name": "Phoenix Dental",
                    "type": "broken_link",
                }
            },
        },
    )
    enrichment = tmp_path / "VERIDRA_AI_ENRICHMENT_TEST.zip"
    _write_zip(
        enrichment,
        {
            "manifest.json": {
                "schema_version": 1,
                "exchange_type": "veridra_ai_enrichment",
                "source_export_id": "export-1",
            },
            "enrichment.json": [
                {
                    "business_name": "Phoenix Dental",
                    "commercial_claims": [
                        {
                            "claim": "The privacy link creates a visible dead end.",
                            "evidence_level": "A",
                            "evidence_refs": ["visual:Phoenix-Dental:1"],
                        },
                        {
                            "claim": "This definitely loses half of all bookings.",
                            "evidence_level": "D",
                            "evidence_refs": ["visual:Phoenix-Dental:1"],
                        },
                    ],
                }
            ],
        },
    )

    output = import_pack(
        enrichment_input=enrichment,
        source_export_input=source_export,
        output_directory=tmp_path,
    )

    with zipfile.ZipFile(output) as archive:
        report = json.loads(archive.read("validation_report.json"))
        normalized = json.loads(archive.read("normalized_enrichment.json"))

    assert report["commercial_claims_accepted"] == 1
    assert report["level_d_claims_suppressed"] == 1
    assert report["claims_rejected"] == 0
    assert report["raw_evidence_mutated"] is False
    assert len(normalized[0]["commercial_ready_claims"]) == 1
    assert len(normalized[0]["analysis_only_claims"]) == 1


def test_import_rejects_unknown_evidence_refs(tmp_path: Path) -> None:
    source_export = tmp_path / "VERIDRA_AI_EXPORT_TEST.zip"
    _write_zip(
        source_export,
        {
            "manifest.json": {
                "schema_version": 1,
                "exchange_type": "veridra_ai_export",
                "export_id": "export-1",
            },
            "evidence_index.json": {},
        },
    )
    enrichment = tmp_path / "VERIDRA_AI_ENRICHMENT_TEST.zip"
    _write_zip(
        enrichment,
        {
            "manifest.json": {
                "schema_version": 1,
                "exchange_type": "veridra_ai_enrichment",
                "source_export_id": "export-1",
            },
            "enrichment.json": [
                {
                    "business_name": "Clinic",
                    "commercial_claims": [
                        {
                            "claim": "Unsupported claim",
                            "evidence_level": "A",
                            "evidence_refs": ["missing:1"],
                        }
                    ],
                }
            ],
        },
    )

    output = import_pack(
        enrichment_input=enrichment,
        source_export_input=source_export,
        output_directory=tmp_path,
    )
    with zipfile.ZipFile(output) as archive:
        report = json.loads(archive.read("validation_report.json"))
        normalized = json.loads(archive.read("normalized_enrichment.json"))

    assert report["claims_rejected"] == 1
    assert normalized[0]["commercial_ready_claims"] == []
    assert normalized[0]["rejected_claims"][0]["rejection_reason"]


def test_import_rejects_wrong_source_export(tmp_path: Path) -> None:
    source_export = tmp_path / "VERIDRA_AI_EXPORT_TEST.zip"
    _write_zip(
        source_export,
        {
            "manifest.json": {
                "schema_version": 1,
                "exchange_type": "veridra_ai_export",
                "export_id": "export-1",
            },
            "evidence_index.json": {},
        },
    )
    enrichment = tmp_path / "VERIDRA_AI_ENRICHMENT_TEST.zip"
    _write_zip(
        enrichment,
        {
            "manifest.json": {
                "schema_version": 1,
                "exchange_type": "veridra_ai_enrichment",
                "source_export_id": "other-export",
            },
            "enrichment.json": [],
        },
    )

    with pytest.raises(ValueError, match="does not match"):
        import_pack(
            enrichment_input=enrichment,
            source_export_input=source_export,
            output_directory=tmp_path,
        )
