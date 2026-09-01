from __future__ import annotations

from datetime import UTC, datetime

from veridra.core import Assessment
from veridra.observations import ObservationRecord, ObservedAssessment


def test_observed_assessment_enriches_direct_observation_provenance() -> None:
    observed_at = datetime(2026, 9, 1, 10, 30, tzinfo=UTC)
    assessment = Assessment.build(
        "https://example.com",
        [],
        generated_at=observed_at,
    )
    record = ObservationRecord(
        key="page.http-status",
        scope="page",
        subject="https://example.com/",
        state="200",
    )

    wrapped = ObservedAssessment.from_assessment(
        assessment,
        observations=(record,),
        collector_version="3.3.0",
        crawl_profile="quick",
    )

    saved = wrapped.observations[0]
    assert saved.observed_at == observed_at
    assert saved.collector_version == "3.3.0"
    assert saved.source_type == "direct"
    assert saved.confidence == "direct"
    assert saved.evidence_refs == ()


def test_explicit_observation_provenance_is_not_overwritten() -> None:
    assessment_time = datetime(2026, 9, 1, 10, 30, tzinfo=UTC)
    explicit_time = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
    assessment = Assessment.build(
        "https://example.com",
        [],
        generated_at=assessment_time,
    )
    record = ObservationRecord(
        key="page.indexable",
        scope="page",
        subject="https://example.com/",
        state="true",
        observed_at=explicit_time,
        collector_version="fixture-collector",
        source_type="direct-static-html",
        confidence="direct",
    )

    wrapped = ObservedAssessment.from_assessment(
        assessment,
        observations=(record,),
        collector_version="3.3.0",
    )

    saved = wrapped.observations[0]
    assert saved.observed_at == explicit_time
    assert saved.collector_version == "fixture-collector"
    assert saved.source_type == "direct-static-html"
