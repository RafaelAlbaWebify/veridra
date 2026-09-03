from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeliveryMilestone(StrEnum):
    working = "working"
    ready_for_review = "ready_for_review"
    revision_in_progress = "revision_in_progress"
    accepted = "accepted"
    handoff = "handoff"
    final_balance = "final_balance"
    closed = "closed"


class CustomerReviewState(StrEnum):
    not_requested = "not_requested"
    awaiting_review = "awaiting_review"
    changes_requested = "changes_requested"
    accepted = "accepted"
    unresponsive = "unresponsive"
    blocked = "blocked"


class RecurringServiceDecision(StrEnum):
    undecided = "undecided"
    offered = "offered"
    accepted = "accepted"
    declined = "declined"
    not_applicable = "not_applicable"


class DeliveryEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    action: str = Field(min_length=1, max_length=120)
    reference: str = Field(default="", max_length=2000)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectDeliveryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: str = Field(min_length=24, max_length=64)
    milestone: DeliveryMilestone = DeliveryMilestone.working
    deliverables: tuple[str, ...] = ()
    completed_deliverables: tuple[str, ...] = ()
    revision_policy: str = Field(default="", max_length=2000)
    included_revisions: int = Field(default=1, ge=0, le=100)
    revisions_used: int = Field(default=0, ge=0, le=100)
    review_state: CustomerReviewState = CustomerReviewState.not_requested
    review_reference: str = Field(default="", max_length=2000)
    acceptance_criteria: str = Field(default="", max_length=4000)
    acceptance_evidence: str = Field(default="", max_length=4000)
    accepted_at: datetime | None = None
    completion_summary: str = Field(default="", max_length=4000)
    handoff_backups: bool = False
    handoff_access: bool = False
    handoff_documentation: bool = False
    handoff_reference: str = Field(default="", max_length=2000)
    final_balance_required: bool = True
    final_balance_evidence: str = Field(default="", max_length=2000)
    recurring_decision: RecurringServiceDecision = RecurringServiceDecision.undecided
    closed_at: datetime | None = None
    reopened_at: datetime | None = None
    reopen_reference: str = Field(default="", max_length=2000)
    events: tuple[DeliveryEvent, ...] = ()
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def handoff_complete(self) -> bool:
        return self.handoff_backups and self.handoff_access and self.handoff_documentation

    @property
    def deliverables_complete(self) -> bool:
        return bool(self.deliverables) and set(self.completed_deliverables) == set(self.deliverables)

    @model_validator(mode="after")
    def validate_state(self) -> ProjectDeliveryRecord:
        if not set(self.completed_deliverables).issubset(set(self.deliverables)):
            raise ValueError("Completed deliverables must exist in the delivery checklist.")
        if self.revisions_used > self.included_revisions and not self.review_reference:
            raise ValueError("Revisions beyond the included allowance require a scope/change reference.")
        if self.milestone is not DeliveryMilestone.working:
            if not self.deliverables_complete or not self.acceptance_criteria:
                raise ValueError("Review requires completed deliverables and acceptance criteria.")
        if self.review_state is CustomerReviewState.accepted:
            if not self.acceptance_evidence or self.accepted_at is None:
                raise ValueError("Customer acceptance requires evidence and an accepted-at timestamp.")
        if self.milestone in {
            DeliveryMilestone.accepted,
            DeliveryMilestone.handoff,
            DeliveryMilestone.final_balance,
            DeliveryMilestone.closed,
        } and self.review_state is not CustomerReviewState.accepted:
            raise ValueError("Accepted and later delivery milestones require customer acceptance.")
        if self.milestone in {DeliveryMilestone.final_balance, DeliveryMilestone.closed}:
            if not self.handoff_complete or not self.handoff_reference:
                raise ValueError("Final balance and closure require completed handoff evidence.")
        if self.milestone is DeliveryMilestone.closed:
            if self.final_balance_required and not self.final_balance_evidence:
                raise ValueError("Closure requires final balance evidence when a balance is required.")
            if not self.completion_summary:
                raise ValueError("Closure requires a completion summary.")
            if self.recurring_decision is RecurringServiceDecision.undecided:
                raise ValueError("Closure requires a recurring-service decision.")
            if self.closed_at is None:
                raise ValueError("Closed projects require a closed-at timestamp.")
        return self


class ProjectDeliveryStoreError(RuntimeError):
    pass


class ProjectDeliveryStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, project_id: str) -> Path:
        return self.directory / f"{project_id}.json"

    def load(self, project_id: str) -> ProjectDeliveryRecord:
        try:
            text = self._path(project_id).read_text(encoding="utf-8")
            return ProjectDeliveryRecord.model_validate_json(text)
        except (OSError, ValueError) as exc:
            raise ProjectDeliveryStoreError(
                "Saved project delivery record was not found or is invalid."
            ) from exc

    def save(self, record: ProjectDeliveryRecord) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            record.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        path = self._path(record.project_id)
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{record.project_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
