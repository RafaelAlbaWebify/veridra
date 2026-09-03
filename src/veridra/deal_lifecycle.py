from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReplyOutcome(StrEnum):
    positive = "positive"
    negative = "negative"
    price_request = "price_request"
    call_request = "call_request"
    different_scope = "different_scope"
    no_response = "no_response"


class ProposalStatus(StrEnum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"


class DiscoveryRequirements(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    goals: str = Field(min_length=1, max_length=4000)
    current_platform: str = Field(default="", max_length=240)
    hosting: str = Field(default="", max_length=240)
    decision_maker: str = Field(default="", max_length=240)
    urgency: str = Field(default="", max_length=500)
    constraints: str = Field(default="", max_length=4000)
    access_readiness: str = Field(default="", max_length=1000)
    measurable_scope: str = Field(min_length=1, max_length=4000)
    deliverables: str = Field(min_length=1, max_length=4000)
    exclusions: str = Field(default="", max_length=4000)
    assumptions: str = Field(default="", max_length=4000)
    timeline: str = Field(min_length=1, max_length=1000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProposalVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    version: int = Field(ge=1)
    status: ProposalStatus = ProposalStatus.draft
    title: str = Field(min_length=1, max_length=240)
    scope: str = Field(min_length=1, max_length=4000)
    deliverables: str = Field(min_length=1, max_length=4000)
    exclusions: str = Field(default="", max_length=4000)
    assumptions: str = Field(default="", max_length=4000)
    timeline: str = Field(min_length=1, max_length=1000)
    price_amount: float = Field(gt=0, le=10_000_000)
    currency: str = Field(min_length=3, max_length=3)
    recurring_amount: float | None = Field(default=None, gt=0, le=10_000_000)
    recurring_cadence: str = Field(default="", max_length=120)
    valid_until: date
    acceptance_reference: str = Field(default="", max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_recurring_pair(self) -> ProposalVersion:
        if self.recurring_amount is not None and not self.recurring_cadence:
            raise ValueError("Recurring proposals require a cadence.")
        if self.recurring_amount is None and self.recurring_cadence:
            raise ValueError("Recurring cadence requires a recurring amount.")
        if self.status is ProposalStatus.accepted and not self.acceptance_reference:
            raise ValueError("Accepted proposals require acceptance evidence/reference.")
        return self


class DealRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    prospect_id: str = Field(min_length=24, max_length=24)
    reply_outcome: ReplyOutcome | None = None
    conversation_summary: str = Field(default="", max_length=4000)
    next_action: str = Field(default="", max_length=1000)
    discovery: DiscoveryRequirements | None = None
    proposals: tuple[ProposalVersion, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def latest_proposal(self) -> ProposalVersion | None:
        return self.proposals[-1] if self.proposals else None

    @property
    def has_accepted_proposal(self) -> bool:
        return any(item.status is ProposalStatus.accepted for item in self.proposals)


class DealStoreError(RuntimeError):
    pass


class DealStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, prospect_id: str) -> Path:
        return self.directory / f"{prospect_id}.json"

    def load(self, prospect_id: str) -> DealRecord:
        try:
            text = self._path(prospect_id).read_text(encoding="utf-8")
            return DealRecord.model_validate_json(text)
        except (OSError, ValueError) as exc:
            raise DealStoreError("Saved deal record was not found or is invalid.") from exc

    def save(self, record: DealRecord) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            record.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        path = self._path(record.prospect_id)
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{record.prospect_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
