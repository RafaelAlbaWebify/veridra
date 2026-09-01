from __future__ import annotations

from datetime import UTC, datetime

from veridra.core import Assessment, Finding, Status
from veridra.history import Comparison
from veridra.progress import build_progress_summary


def _assessment(*findings: Finding) -> Assessment:
    return Assessment.build(
        "https://example.com",
        list(findings),
        generated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def _finding(
    finding_id: str,
    *,
    status: Status = Status.attention,
    severity: str = "medium",
) -> Finding:
    return Finding(
        id=finding_id,
        area="Website health",
        title=finding_id,
        status=status,
        severity=severity,
        summary="Observed.",
    )


def test_progress_uses_stable_finding_ids_for_lifecycle_groups() -> None:
    before = _assessment(
        _finding("finding.persist"),
        _finding("finding.resolve"),
        _finding("finding.state", status=Status.attention, severity="high"),
    )
    after = _assessment(
        _finding("finding.persist"),
        _finding("finding.new"),
        _finding("finding.state", status=Status.passed, severity="info"),
    )
    comparison = Comparison(
        before_id="a" * 24,
        after_id="b" * 24,
        added=("finding.new",),
        resolved=("finding.resolve",),
        changed=("finding.state",),
        unchanged=("finding.persist",),
        page_history_available=True,
        pages_added=("https://example.com/new",),
        pages_removed=("https://example.com/old",),
        pages_changed=("https://example.com/",),
        page_status_changed=("https://example.com/old",),
    )

    summary = build_progress_summary(before, after, comparison)

    assert summary.new_findings == ("finding.new",)
    assert summary.resolved_findings == ("finding.resolve",)
    assert summary.persistent_findings == ("finding.persist", "finding.state")
    assert len(summary.state_changes) == 1
    change = summary.state_changes[0]
    assert change.finding_id == "finding.state"
    assert change.before_status == "attention"
    assert change.after_status == "passed"
    assert change.before_severity == "high"
    assert change.after_severity == "info"
    assert summary.pages_added == ("https://example.com/new",)
    assert summary.pages_removed == ("https://example.com/old",)
    assert summary.pages_changed == ("https://example.com/",)
    assert summary.page_status_changed == ("https://example.com/old",)
    assert summary.page_history_available is True


def test_progress_does_not_call_legacy_page_history_zero_change() -> None:
    before = _assessment(_finding("finding.persist"))
    after = _assessment(_finding("finding.persist"))
    comparison = Comparison(
        before_id="a" * 24,
        after_id="b" * 24,
        added=(),
        resolved=(),
        changed=(),
        unchanged=("finding.persist",),
        page_history_available=False,
    )

    summary = build_progress_summary(before, after, comparison)

    assert summary.persistent_findings == ("finding.persist",)
    assert summary.page_history_available is False
    assert summary.pages_added == ()
    assert summary.pages_removed == ()
    assert summary.pages_changed == ()
    assert summary.page_status_changed == ()
