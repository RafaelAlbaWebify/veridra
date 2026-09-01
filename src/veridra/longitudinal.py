from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from .core import Assessment
from .observations import ObservationRecord


@dataclass(frozen=True)
class LifecycleMetadata:
    """First/last-seen values bounded to genuinely stored comparable history."""

    identity: str
    first_seen: datetime | None
    last_seen: datetime | None
    history_available: bool
    basis: str


def _ordered(assessments: Iterable[Assessment]) -> tuple[Assessment, ...]:
    return tuple(sorted(assessments, key=lambda item: item.generated_at))


def finding_lifecycle(
    assessments: Iterable[Assessment],
) -> tuple[LifecycleMetadata, ...]:
    """Derive finding lifecycle from stable finding IDs in retained assessments.

    Legacy assessments still contain findings, so they remain valid evidence. The
    timestamps are explicitly bounded to retained assessment history and are not
    claims about time before the oldest stored assessment.
    """

    seen: defaultdict[str, list[datetime]] = defaultdict(list)
    for assessment in _ordered(assessments):
        for finding in assessment.findings:
            seen[finding.id].append(assessment.generated_at)
    return tuple(
        LifecycleMetadata(
            identity=finding_id,
            first_seen=min(timestamps),
            last_seen=max(timestamps),
            history_available=True,
            basis="retained_assessment_history",
        )
        for finding_id, timestamps in sorted(seen.items())
    )


def _observation_identity(record: ObservationRecord) -> str:
    return f"{record.scope}:{record.subject}:{record.key}"


def observation_lifecycle(
    assessments: Iterable[Assessment],
) -> tuple[LifecycleMetadata, ...]:
    """Derive observation lifecycle only when the retained history supports it.

    If any retained assessment predates the normalized observation layer, the
    observation timeline is incomplete. In that case identities visible in the
    observation-capable assessments are returned with first/last seen explicitly
    unknown rather than fabricating a start or end date.
    """

    ordered = _ordered(assessments)
    records_by_identity: defaultdict[str, list[datetime]] = defaultdict(list)
    complete = bool(ordered) and all(
        getattr(assessment, "collector_version", None) is not None
        and hasattr(assessment, "observations")
        for assessment in ordered
    )

    for assessment in ordered:
        records = getattr(assessment, "observations", ())
        for record in records:
            if not isinstance(record, ObservationRecord):
                continue
            timestamp = record.observed_at or assessment.generated_at
            records_by_identity[_observation_identity(record)].append(timestamp)

    return tuple(
        LifecycleMetadata(
            identity=identity,
            first_seen=min(timestamps) if complete else None,
            last_seen=max(timestamps) if complete else None,
            history_available=complete,
            basis=(
                "retained_observation_history"
                if complete
                else "observation_history_incomplete"
            ),
        )
        for identity, timestamps in sorted(records_by_identity.items())
    )
