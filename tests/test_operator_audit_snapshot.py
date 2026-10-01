from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path


def test_operator_audit_snapshot_summarizes_prospect_quality(tmp_path: Path) -> None:
    tenant_root = tmp_path / "tenants"
    prospects = tenant_root / "webify" / "prospects"
    prospects.mkdir(parents=True)
    (prospects / "a.json").write_text(
        json.dumps(
            {
                "business_name": "Alpha Notary",
                "status": "needs_review",
                "sector": "",
                "website": None,
                "provider": "google_maps",
                "qualification": None,
                "discovery": {
                    "opportunity_score": 71,
                    "opportunity_band": "priority",
                },
            }
        ),
        encoding="utf-8",
    )
    (prospects / "b.json").write_text(
        json.dumps(
            {
                "business_name": "Beta Solicitors",
                "status": "qualified",
                "sector": "Solicitor",
                "website": "https://example.test/",
                "provider": "google_maps",
                "qualification": {"score": 12},
                "discovery": None,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "snapshot.zip"

    completed = subprocess.run(
        [
            sys.executable,
            "tools/operator_audit_snapshot.py",
            "--tenant-data-root",
            str(tenant_root),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    with zipfile.ZipFile(output) as archive:
        summary = json.loads(archive.read("audit-summary.json"))

    prospects_summary = summary["tenants"]["webify"]["prospects"]
    assert prospects_summary["count"] == 2
    assert prospects_summary["quality"]["missing_sector"] == 1
    assert prospects_summary["quality"]["missing_website"] == 1
    assert prospects_summary["quality"]["structured_discovery"] == 1
    assert prospects_summary["quality"]["legacy_discovery_recoverable"] == 0
    assert prospects_summary["quality"]["missing_discovery_unrecoverable"] == 1
    assert prospects_summary["quality"]["missing_qualification"] == 1
    assert prospects_summary["discovery_band_counts"]["priority"] == 1
