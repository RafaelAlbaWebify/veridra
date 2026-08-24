from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from veridra.collector import PageEvidence
from veridra.prospect_qualification_evidence_cli import (
    QualificationTarget,
    _aggregate,
    _build_archive,
    _page_signals,
    qualify_target,
)


def _page(url: str, body: str, status: int = 200) -> PageEvidence:
    return PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=status,
        headers={"content-type": "text/html; charset=utf-8"},
        body=body,
        redirect_chain=(),
        connected_ip="203.0.113.10",
        validated_ips=("203.0.113.10",),
    )


def _target() -> QualificationTarget:
    return QualificationTarget(
        result_rank=2,
        name="Example Dental",
        audit_url="https://example.ie/",
        audit_status="success",
        technical_finding_weight=42,
        attention_findings=12,
        shared_hostname=False,
    )


def test_page_signals_extract_contact_and_review_clues() -> None:
    page = _page(
        "https://example.ie/",
        """
        <html><body>
        <a href="mailto:hello@example.ie">Email us</a>
        <a href="tel:+35315551234">Call</a>
        <a href="/book-appointment">Book appointment</a>
        <a href="/our-team">Our team</a>
        <a href="https://instagram.com/example">Instagram</a>
        <p>Dr Jane Murphy - Principal Dentist</p>
        <p>We are part of the Example Dental Group.</p>
        </body></html>
        """,
    )

    signals, links = _page_signals(page)

    assert signals.emails == ("hello@example.ie",)
    assert signals.phones == ("+35315551234",)
    assert signals.appointment_urls == ("https://example.ie/book-appointment",)
    assert signals.social_urls == ("https://instagram.com/example",)
    assert "Dr Jane Murphy - Principal Dentist" in signals.role_snippets
    assert "We are part of the Example Dental Group." in signals.group_snippets
    assert "https://example.ie/our-team" in links
    assert "https://example.ie/book-appointment" in links


def test_qualify_target_is_bounded_and_keeps_source_evidence() -> None:
    pages = {
        "https://example.ie/": _page(
            "https://example.ie/",
            '<a href="/contact">Contact</a><a href="/team">Team</a>',
        ),
        "https://example.ie/contact": _page(
            "https://example.ie/contact",
            '<a href="mailto:hello@example.ie">hello@example.ie</a>',
        ),
        "https://example.ie/team": _page(
            "https://example.ie/team",
            "<p>Mary Smith, Practice Manager</p>",
        ),
    }
    calls: list[str] = []

    def collector(url: str) -> PageEvidence:
        calls.append(url)
        return pages[url]

    outcome = qualify_target(
        _target(),
        collector=collector,
        max_pages=2,
        top_audit_findings=(
            {"id": "a", "severity": "high", "area": "Accessibility", "title": "Issue", "summary": "Observed."},
        ),
    )
    row = _aggregate(outcome)

    assert calls == ["https://example.ie/", "https://example.ie/contact"]
    assert row["pages_collected"] == 2
    assert row["emails"] == ["hello@example.ie"]
    assert row["review_state"] == "ready_for_manual_qualification"
    assert row["top_audit_findings"]


def test_archive_is_read_only_and_contains_per_prospect_evidence(tmp_path: Path) -> None:
    source = tmp_path / "VERIDRA_PROSPECT_AUDITS_test.zip"
    source.write_bytes(b"audit-evidence")
    outcome = qualify_target(
        _target(),
        collector=lambda url: _page(
            url,
            '<a href="mailto:hello@example.ie">Email</a><p>John Doe, Owner</p>',
        ),
        max_pages=1,
    )

    payload = _build_archive(
        source_path=source,
        outcomes=[outcome],
        generated_at="2026-08-24T03:30:00+00:00",
        max_pages_per_site=4,
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        summary = json.loads(archive.read("qualification_summary.json"))

    assert "qualification_summary.csv" in names
    assert "prospects/02-Example-Dental.json" in names
    assert manifest["persistence"] == "none"
    assert manifest["outreach"] == "none"
    assert manifest["source_audit_sha256"]
    assert summary[0]["emails"] == ["hello@example.ie"]
    assert summary[0]["role_snippets"] == ["John Doe, Owner"]
