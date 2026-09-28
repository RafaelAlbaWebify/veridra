from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from veridra.task_store import (
    RemediationTask,
    TaskStatus,
    TaskStore,
    TaskStoreError,
    task_id,
)

PROJECT_ID = "a" * 24
ASSESSMENT_ID = "b" * 24


def _task(**changes: object) -> RemediationTask:
    values: dict[str, object] = {
        "project_id": PROJECT_ID,
        "finding_id": "health.title",
        "title": "Add a descriptive title",
        "status": TaskStatus.open,
        "notes": "Review the homepage title.",
        "owner_label": "Web team",
        "due_date": "2026-08-15",
        "source_assessment_id": ASSESSMENT_ID,
    }
    values.update(changes)
    return RemediationTask.model_validate(values)


def test_save_load_list_filter_replace_and_delete(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    original = _task()

    identifier = store.save(original)
    assert identifier == task_id(original)
    assert store.load(identifier) == original
    assert store.save(original) == identifier
    assert store.list(project_id=PROJECT_ID) == [(identifier, original)]
    assert store.list(status=TaskStatus.planned) == []

    updated = _task(status=TaskStatus.planned, notes="Scheduled for next sprint.")
    new_identifier = store.replace(identifier, updated)
    assert new_identifier != identifier
    assert store.load(new_identifier) == updated
    with pytest.raises(TaskStoreError, match="not found"):
        store.load(identifier)

    store.delete(new_identifier)
    assert store.list() == []


def test_unknown_fields_and_statuses_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RemediationTask.model_validate(
            {
                **_task().model_dump(),
                "unexpected": "value",
            }
        )
    with pytest.raises(ValidationError):
        _task(status="done")


def test_identifiers_are_validated(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    with pytest.raises(TaskStoreError, match="Invalid task identifier"):
        store.load("../escape")


def test_corrupt_files_are_skipped_safely(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{'c' * 24}.json").write_text("not-json", encoding="utf-8")
    assert TaskStore(tmp_path).list() == []


def test_all_supported_statuses_round_trip(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    for status in TaskStatus:
        verification = (
            {
                "verification_assessment_id": "c" * 24,
                "verification_evidence": "Later assessment confirms the finding is resolved.",
            }
            if status is TaskStatus.verified
            else {}
        )
        task = _task(
            status=status,
            finding_id=f"finding.{status.value}",
            **verification,
        )
        identifier = store.save(task)
        assert store.load(identifier).status == status


def test_verified_status_requires_later_assessment_and_evidence() -> None:
    with pytest.raises(ValidationError, match="re-assessment reference"):
        _task(status=TaskStatus.verified)
    with pytest.raises(ValidationError, match="later assessment"):
        _task(
            status=TaskStatus.verified,
            verification_assessment_id=ASSESSMENT_ID,
            verification_evidence="Checked again.",
        )
    verified = _task(
        status=TaskStatus.verified,
        verification_assessment_id="c" * 24,
        verification_evidence="Later assessment no longer contains the source finding.",
    )
    assert verified.status is TaskStatus.verified
