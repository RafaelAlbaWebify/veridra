from __future__ import annotations

from dataclasses import dataclass

from .core import Assessment
from .history import Comparison


@dataclass(frozen=True)
class FindingStateChange:
    finding_id: str
    before_status: str
    after_status: str
    before_severity: str
    after_severity: str


@dataclass(frozen=True)
class ProgressSummary:
    new_findings: tuple[str, ...]
    resolved_findings: tuple[str, ...]
    persistent_findings: tuple[str, ...]
    state_changes: tuple[FindingStateChange, ...]
    pages_added: tuple[str, ...]
    pages_removed: tuple[str, ...]
    pages_changed: tuple[str, ...]
    page_status_changed: tuple[str, ...]
    page_history_available: bool


def build_progress_summary(
    before: Assessment,
    after: Assessment,
    comparison: Comparison,
) -> ProgressSummary:
    before_findings = {item.id: item for item in before.findings}
    after_findings = {item.id: item for item in after.findings}
    common_ids = set(before_findings) & set(after_findings)
    state_changes = tuple(
        FindingStateChange(
            finding_id=finding_id,
            before_status=before_findings[finding_id].status.value,
            after_status=after_findings[finding_id].status.value,
            before_severity=before_findings[finding_id].severity,
            after_severity=after_findings[finding_id].severity,
        )
        for finding_id in sorted(common_ids)
        if (
            before_findings[finding_id].status != after_findings[finding_id].status
            or before_findings[finding_id].severity != after_findings[finding_id].severity
        )
    )
    return ProgressSummary(
        new_findings=comparison.added,
        resolved_findings=comparison.resolved,
        persistent_findings=tuple(sorted(common_ids)),
        state_changes=state_changes,
        pages_added=comparison.pages_added,
        pages_removed=comparison.pages_removed,
        pages_changed=comparison.pages_changed,
        page_status_changed=comparison.page_status_changed,
        page_history_available=comparison.page_history_available,
    )
