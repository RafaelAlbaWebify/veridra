from __future__ import annotations

import hashlib
import json
import os
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field


class TaskStoreError(RuntimeError):
    pass


class TaskStatus(StrEnum):
    open = "open"
    planned = "planned"
    in_progress = "in_progress"
    fixed = "fixed"
    ignored = "ignored"
    accepted_risk = "accepted_risk"
    verification_required = "verification_required"
    verified = "verified"


class RemediationTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    finding_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    status: TaskStatus = TaskStatus.open
    notes: str = Field(default="", max_length=5000)
    owner_label: str = Field(default="", max_length=120)
    due_date: str = Field(default="", max_length=40)
    source_assessment_id: str = Field(pattern=r"^[0-9a-f]{24}$")


def default_task_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve() / "tasks"
    return Path.home() / ".veridra" / "tasks"


def _canonical_bytes(task: RemediationTask) -> bytes:
    return json.dumps(
        task.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def task_id(task: RemediationTask) -> str:
    return hashlib.sha256(_canonical_bytes(task)).hexdigest()[:24]


class TaskStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_task_directory()

    def _path(self, identifier: str) -> Path:
        valid = len(identifier) == 24 and all(
            char in "0123456789abcdef" for char in identifier
        )
        if not valid:
            raise TaskStoreError("Invalid task identifier.")
        return self.directory / f"{identifier}.json"

    def save(self, task: RemediationTask) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        identifier = task_id(task)
        destination = self._path(identifier)
        if destination.exists():
            return identifier
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{identifier}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(_canonical_bytes(task))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return identifier

    def load(self, identifier: str) -> RemediationTask:
        path = self._path(identifier)
        try:
            return RemediationTask.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise TaskStoreError("Saved remediation task was not found.") from exc
        except (OSError, ValueError) as exc:
            raise TaskStoreError("Saved remediation task could not be read safely.") from exc

    def list(
        self,
        *,
        project_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[tuple[str, RemediationTask]]:
        if not self.directory.exists():
            return []
        tasks: list[tuple[str, RemediationTask]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                task = RemediationTask.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            if project_id is not None and task.project_id != project_id:
                continue
            if status is not None and task.status != status:
                continue
            tasks.append((path.stem, task))
        return sorted(
            tasks,
            key=lambda item: (
                item[1].project_id,
                item[1].status.value,
                item[1].title.lower(),
                item[0],
            ),
        )

    def replace(self, identifier: str, task: RemediationTask) -> str:
        old_path = self._path(identifier)
        if not old_path.exists():
            raise TaskStoreError("Saved remediation task was not found.")
        new_identifier = self.save(task)
        if new_identifier != identifier:
            old_path.unlink()
        return new_identifier

    def delete(self, identifier: str) -> None:
        try:
            self._path(identifier).unlink()
        except FileNotFoundError as exc:
            raise TaskStoreError("Saved remediation task was not found.") from exc
