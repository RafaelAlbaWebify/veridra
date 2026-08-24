from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from veridra.core import Assessment, Finding, Status
from veridra.prospect_audit_evidence_cli import (
    AuditOutcome,
    AuditTarget,
    _build_archive,
    _ranking_rows,
    canonicalize_audit_url,
    technical_opportunity_score,
)


def _assessment(target: str, *, high: int = 0, medium: int = 0, unavailable: int = 0) -> Assessment:
    findings: list[Finding] = []
    for index in range(high):
        findings.append(
            Finding(
                id=f"high-{index}",
                area="Website health",
                title="High issue",
                status=Status.attention,
                severity="high",
                summary="Observed high issue.",
            )
        )
    for index in range(medium):
        findings.append(
            Finding(
                id=f"medium-{index}",
                area="Search visibility",
                title="Medium issue",
                status=Status.attention,
                severity="medium",
                summary="Observed medium issue.",
            )
        )
    for index in range(unavailable):
        findings.append(
            Finding(
                id=f"unavailable-{index}",
                area="Website health",
                title="Unavailable evidence",
                status=Status.unavailable,
                severity="high",
                summary="Evidence unavailable.",
            )
        )
    return Assessment.build(
        target,
        findings,
        generated_at=datetime(2026, 8, 24, tzinfo=UTC),
    )


def _target(rank: int, name: str, website: str) -> AuditTarget:
    return AuditTarget(
        result_rank=rank,
        name=name,
        source_url=f"https://www.google.com/maps/place/{name}",
        captured_website=website,
        audit_url=canonicalize_audit_url(website),
        provider_key=f"google-maps:{rank}",
    )


def test_canonicalize_audit_url_strips_tracking_but_preserves_meaningful_query() -> None:
    value = (
        "https://Example.ie/path/?utm_source=maps&service=implant&y_source=abc"
        "&UTM_MEDIUM=organic#contact"
    )
    assert canonicalize_audit_url(value) == "https://example.ie/path/?service=implant"


def test_technical_opportunity_score_ignores_unavailable_findings() -> None:
    assessment = _assessment("https://clinic.ie/", high=1, medium=2, unavailable=3)
    assert technical_opportunity_score(assessment) == 11


def test_ranking_orders_successful_targets_by_technical_opportunity() -> None:
    first = _target(1, "First", "https://shared.ie/?utm_source=maps")
    second = _target(2, "Second", "https://shared.ie/location")
    failed = _target(3, "Failed", "https://failed.ie/")
    rows = _ranking_rows(
        [
            AuditOutcome(first, _assessment(first.audit_url, medium=1)),
            AuditOutcome(second, _assessment(second.audit_url, high=1)),
            AuditOutcome(failed, None, error="timeout"),
        ]
    )
    assert [row["name"] for row in rows] == ["Second", "First", "Failed"]
    assert rows[0]["technical_opportunity_score"] == 5
    assert rows[0]["shared_hostname"] is True
    assert rows[0]["shared_hostname_count"] == 2
    assert rows[-1]["audit_status"] == "failed"


def test_build_archive_contains_rankings_assessments_and_nested_evidence() -> None:
    target = _target(2, "Slievemore Dental", "https://www.slievemoredental.ie/")
    assessment = _assessment(target.audit_url, medium=1)
    payload = _build_archive(
        source_path=Path("VERIDRA_DISCOVERY_dentist-in-Dublin-IE.zip"),
        outcomes=[AuditOutcome(target, assessment)],
        generated_at="2026-08-24T03:00:00+00:00",
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        ranking = json.loads(archive.read("audit_ranking.json"))

    assert "audit_summary.csv" in names
    assert "assessments/02-Slievemore-Dental.json" in names
    assert "evidence/02-Slievemore-Dental.zip" in names
    assert manifest["persistence"] == "none"
    assert manifest["score_model"]["unavailable_findings_scored"] is False
    assert ranking[0]["technical_opportunity_score"] == 3
