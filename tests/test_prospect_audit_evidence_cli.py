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
    run_batch,
    technical_finding_weight,
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


def test_technical_finding_weight_ignores_unavailable_findings() -> None:
    assessment = _assessment("https://clinic.ie/", high=1, medium=2, unavailable=3)
    assert technical_finding_weight(assessment) == 11


def test_ranking_orders_successful_targets_by_technical_weight() -> None:
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
    assert rows[0]["technical_finding_weight"] == 5
    assert rows[0]["shared_hostname"] is True
    assert rows[0]["shared_hostname_count"] == 2
    assert rows[-1]["audit_status"] == "failed"


def test_run_batch_audits_duplicate_normalized_url_only_once() -> None:
    first = _target(1, "First location", "https://shared.ie/?utm_source=maps")
    second = _target(2, "Second location", "https://shared.ie/")
    calls: list[str] = []

    def assessor(url: str) -> Assessment:
        calls.append(url)
        return _assessment(url, medium=1)

    outcomes = run_batch([first, second], assessor=assessor)

    assert calls == ["https://shared.ie/"]
    assert len(outcomes) == 2
    assert outcomes[0].assessment is outcomes[1].assessment


def test_run_batch_keeps_processing_after_one_site_fails() -> None:
    failed = _target(1, "Failed", "https://failed.ie/")
    good = _target(2, "Good", "https://good.ie/")

    def assessor(url: str) -> Assessment:
        if "failed.ie" in url:
            raise RuntimeError("timeout")
        return _assessment(url, high=1)

    outcomes = run_batch([failed, good], assessor=assessor)

    assert outcomes[0].assessment is None
    assert outcomes[0].error == "timeout"
    assert outcomes[1].assessment is not None


def test_build_archive_contains_unique_site_evidence_and_business_rows(tmp_path: Path) -> None:
    source_path = tmp_path / "VERIDRA_DISCOVERY_dentist-in-Dublin-IE.zip"
    source_path.write_bytes(b"discovery-evidence")
    first = _target(1, "First location", "https://shared.ie/?utm_source=maps")
    second = _target(2, "Second location", "https://shared.ie/")
    assessment = _assessment(first.audit_url, medium=1)
    payload = _build_archive(
        source_path=source_path,
        outcomes=[AuditOutcome(first, assessment), AuditOutcome(second, assessment)],
        generated_at="2026-08-24T03:00:00+00:00",
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        ranking = json.loads(archive.read("audit_ranking.json"))

    assert "audit_summary.csv" in names
    assert "assessments/01-First-location.json" in names
    assert "evidence/01-First-location.zip" in names
    assert "assessments/02-Second-location.json" not in names
    assert manifest["persistence"] == "none"
    assert manifest["business_targets"] == 2
    assert manifest["unique_audit_urls"] == 1
    assert manifest["unique_successful_site_audits"] == 1
    assert manifest["source_discovery_sha256"]
    assert manifest["technical_sort_weight"]["unavailable_findings_weighted"] is False
    assert len(ranking) == 2
    assert ranking[0]["technical_finding_weight"] == 3
