from __future__ import annotations

from datetime import UTC, datetime, timedelta

from veridra.core import Assessment, Finding, Status
from veridra.longitudinal import finding_lifecycle, observation_lifecycle
from veridra.observations import ObservationRecord, ObservedAssessment

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _finding(finding_id: str) -> Finding:
    return Finding(
        id=finding_id,
        area="Website health",
        title=finding_id,
        status=Status.attention,
        severity="medium",
        summary="Observed.",
    )


def _base(at: datetime, *finding_ids: str) -> Assessment:
    return Assessment.build(
        "https://example.com",
        [_finding(finding_id) for finding_id in finding_ids],
        generated_at=at,
    )


def _observed(at: datetime, state: str = "200") -> ObservedAssessment:
    base = _base(at, "finding.persist")
    return ObservedAssessment.from_assessment(
        base,
        observations=(
            ObservationRecord(
                key="page.http-status",
                scope="page",
                subject="https://example.com/",
                state=state,
            ),
        ),
        collector_version="test",
        crawl_profile="quick",
    )


def test_finding_lifecycle_uses_legacy_and_current_retained_assessments() -> None:
    assessments = (
        _base(BASE, "finding.old", "finding.persist"),
        _base(BASE + timedelta(hours=1), "finding.persist", "finding.new"),
    )

    lifecycle = {item.identity: item for item in finding_lifecycle(assessments)}

    assert lifecycle["finding.old"].first_seen == BASE
    assert lifecycle["finding.old"].last_seen == BASE
    assert lifecycle["finding.persist"].first_seen == BASE
    assert lifecycle["finding.persist"].last_seen == BASE + timedelta(hours=1)
    assert lifecycle["finding.new"].first_seen == BASE + timedelta(hours=1)
    assert lifecycle["finding.persist"].basis == "retained_assessment_history"
    assert lifecycle["finding.persist"].history_available is True


def test_observation_lifecycle_is_known_when_all_retained_history_is_comparable() -> None:
    first = _observed(BASE)
    second = _observed(BASE + timedelta(hours=1), state="404")

    lifecycle = observation_lifecycle((second, first))

    assert len(lifecycle) == 1
    item = lifecycle[0]
    assert item.identity == "page:https://example.com/:page.http-status"
    assert item.first_seen == BASE
    assert item.last_seen == BASE + timedelta(hours=1)
    assert item.history_available is True
    assert item.basis == "retained_observation_history"


def test_legacy_gap_forces_observation_first_and_last_seen_unknown() -> None:
    legacy = _base(BASE, "finding.persist")
    current = _observed(BASE + timedelta(hours=1))

    lifecycle = observation_lifecycle((legacy, current))

    assert len(lifecycle) == 1
    item = lifecycle[0]
    assert item.first_seen is None
    assert item.last_seen is None
    assert item.history_available is False
    assert item.basis == "observation_history_incomplete"
