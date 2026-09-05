from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from veridra.prospect_audit_evidence_cli import (
    AuditOutcome,
    AuditTarget,
    _build_archive,
    _ranking_rows,
    canonicalize_audit_url,
    classify_audit_failure,
)


def _target(rank: int, name: str, website: str) -> AuditTarget:
    return AuditTarget(
        result_rank=rank,
        name=name,
        source_url=f"https://example.invalid/source/{rank}",
        captured_website=website,
        audit_url=canonicalize_audit_url(website),
        provider_key=f"validation:{rank}",
    )


def test_dns_failure_is_target_observation() -> None:
    failure = classify_audit_failure("The hostname could not be resolved: dentist.example")
    assert failure["failure_kind"] == "target_dns_resolution_failure"
    assert failure["failure_scope"] == "target_observation"
    assert failure["severity"] == "high"
    assert "DNS" in failure["recommendation"]


def test_tls_failure_is_target_observation_without_bypass_recommendation() -> None:
    failure = classify_audit_failure(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate"
    )
    assert failure["failure_kind"] == "target_tls_certificate_failure"
    assert failure["failure_scope"] == "target_observation"
    assert "does not bypass certificate verification" in failure["recommendation"]


def test_unclassified_runtime_failure_is_not_customer_defect() -> None:
    failure = classify_audit_failure("unexpected parser invariant")
    assert failure["failure_kind"] == "internal_or_unclassified_audit_failure"
    assert failure["failure_scope"] == "internal_failure"
    assert "not classified as a customer website defect" in failure["customer_safe_summary"]


def test_failure_rows_include_scope_and_customer_safe_summary() -> None:
    target = _target(1, "DNS failure", "https://dns-failure.example/")
    rows = _ranking_rows(
        [AuditOutcome(target, None, error="The hostname could not be resolved: dns-failure.example")]
    )
    assert rows[0]["audit_status"] == "failed"
    assert rows[0]["failure_kind"] == "target_dns_resolution_failure"
    assert rows[0]["failure_scope"] == "target_observation"
    assert rows[0]["customer_safe_summary"]


def test_archive_writes_per_target_failure_evidence(tmp_path: Path) -> None:
    source_path = tmp_path / "VERIDRA_DISCOVERY_test.zip"
    source_path.write_bytes(b"discovery-evidence")
    dns = _target(1, "DNS failure", "https://dns-failure.example/")
    tls = _target(2, "TLS failure", "https://tls-failure.example/")
    payload = _build_archive(
        source_path=source_path,
        outcomes=[
            AuditOutcome(dns, None, error="The hostname could not be resolved: dns-failure.example"),
            AuditOutcome(
                tls,
                None,
                error="certificate verify failed: self-signed certificate",
            ),
        ],
        generated_at="2026-09-05T08:30:00+00:00",
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        dns_evidence = json.loads(archive.read("failure-evidence/01-DNS-failure.json"))
        tls_evidence = json.loads(archive.read("failure-evidence/02-TLS-failure.json"))

    assert manifest["schema_version"] == 2
    assert manifest["structured_target_observation_failures"] == 2
    assert "failure-evidence/01-DNS-failure.json" in names
    assert "failure-evidence/02-TLS-failure.json" in names
    assert dns_evidence["failure_kind"] == "target_dns_resolution_failure"
    assert tls_evidence["failure_kind"] == "target_tls_certificate_failure"
    assert "No DNS/TLS safety bypass" in tls_evidence["safety_boundary"]
