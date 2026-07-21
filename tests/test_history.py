from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from veridra.core import Assessment, Finding, Status
from veridra.history import HistoryError, HistoryStore, assessment_id


def _assessment(
    title: str,
    *,
    generated_at: datetime,
    include_extra: bool = False,
) -> Assessment:
    findings = [
        Finding(
            id="health.title",
            area="Website health",
            title=title,
            status=Status.attention,
            severity="medium",
            summary="Needs attention.",
            recommendation="Fix it.",
        )
    ]
    if include_extra:
        findings.append(
            Finding(
                id="security.hsts",
                area="Security posture",
                title="HSTS",
                status=Status.passed,
                severity="info",
                summary="Present.",
            )
        )
    return Assessment.build(
        "https://example.com",
        findings,
        generated_at=generated_at,
    )


def test_save_is_deterministic_and_atomic(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    assessment = _assessment("Title", generated_at=datetime(2026, 1, 1, tzinfo=UTC))

    first = store.save(assessment)
    second = store.save(assessment)

    assert first == second == assessment_id(assessment)
    assert (tmp_path / f"{first}.json").is_file()
    assert not list(tmp_path.glob("*.tmp"))
    assert store.load(first) == assessment


def test_list_is_newest_first(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    older = _assessment("Older", generated_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _assessment("Newer", generated_at=datetime(2026, 1, 2, tzinfo=UTC))
    older_id = store.save(older)
    newer_id = store.save(newer)

    entries = store.list()

    assert [entry.id for entry in entries] == [newer_id, older_id]
    assert entries[0].target == "https://example.com/"


def test_compare_classifies_changes(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    before = _assessment("Old title", generated_at=datetime(2026, 1, 1, tzinfo=UTC))
    after = _assessment(
        "New title",
        generated_at=datetime(2026, 1, 2, tzinfo=UTC),
        include_extra=True,
    )
    before_id = store.save(before)
    after_id = store.save(after)

    comparison = store.compare(before_id, after_id)

    assert comparison.changed == ("health.title",)
    assert comparison.added == ("security.hsts",)
    assert comparison.resolved == ()
    assert comparison.unchanged == ()


def test_prune_and_delete(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    identifiers = [
        store.save(_assessment(f"Title {index}", generated_at=base + timedelta(days=index)))
        for index in range(3)
    ]

    removed = store.prune(keep=1)

    assert set(removed) == set(identifiers[:2])
    assert [entry.id for entry in store.list()] == [identifiers[2]]
    store.delete(identifiers[2])
    assert store.list() == []


def test_invalid_identifier_and_missing_entry(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    with pytest.raises(HistoryError, match="Invalid"):
        store.load("../unsafe")
    with pytest.raises(HistoryError, match="not found"):
        store.load("0" * 24)
    with pytest.raises(HistoryError, match="negative"):
        store.prune(-1)
