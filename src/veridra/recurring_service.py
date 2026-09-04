from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecurringServiceStatus(StrEnum):
    draft = "draft"
    offered = "offered"
    active = "active"
    paused = "paused"
    payment_blocked = "payment_blocked"
    cancellation_pending = "cancellation_pending"
    cancelled = "cancelled"
    expired = "expired"


class BillingCadence(StrEnum):
    monthly = "monthly"
    quarterly = "quarterly"
    annually = "annually"


class RenewalBehavior(StrEnum):
    manual = "manual"
    auto_renew = "auto_renew"
    fixed_term = "fixed_term"


class RecurringServiceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    action: str = Field(min_length=1, max_length=120)
    reference: str = Field(default="", max_length=2000)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecurringServiceVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    version: int = Field(ge=1)
    scope: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    deliverables: tuple[str, ...] = ()
    cadence_description: str = Field(default="", max_length=1000)
    response_time: str = Field(default="", max_length=500)
    escalation_expectations: str = Field(default="", max_length=1000)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    billing_cadence: BillingCadence = BillingCadence.monthly
    effective_from: date | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_commercial_terms(self) -> RecurringServiceVersion:
        if self.currency.upper() != self.currency:
            raise ValueError("Currency must use an uppercase ISO-style code.")
        if self.fee > 0 and not self.scope:
            raise ValueError("Paid recurring service requires a bounded service scope.")
        return self


class RecurringServiceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: str = Field(min_length=24, max_length=64)
    customer_id: str = Field(min_length=24, max_length=64)
    status: RecurringServiceStatus = RecurringServiceStatus.draft
    versions: tuple[RecurringServiceVersion, ...] = ()
    current_version: int | None = None
    offered_at: datetime | None = None
    accepted_at: datetime | None = None
    acceptance_reference: str = Field(default="", max_length=2000)
    start_date: date | None = None
    minimum_term_months: int = Field(default=0, ge=0, le=120)
    renewal_behavior: RenewalBehavior = RenewalBehavior.manual
    renewal_date: date | None = None
    renewal_reference: str = Field(default="", max_length=2000)
    next_billing_date: date | None = None
    invoice_reference: str = Field(default="", max_length=240)
    payment_reference: str = Field(default="", max_length=240)
    last_payment_state: str = Field(default="", max_length=120)
    monitoring_cadence: str = Field(default="", max_length=500)
    report_cadence: str = Field(default="", max_length=500)
    next_action: str = Field(default="", max_length=1000)
    completed_deliverables: tuple[str, ...] = ()
    overage_reference: str = Field(default="", max_length=2000)
    pause_reference: str = Field(default="", max_length=2000)
    cancellation_notice_date: date | None = None
    cancellation_effective_date: date | None = None
    cancellation_reference: str = Field(default="", max_length=2000)
    exit_handoff_reference: str = Field(default="", max_length=2000)
    events: tuple[RecurringServiceEvent, ...] = ()
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def active_version(self) -> RecurringServiceVersion | None:
        if self.current_version is None:
            return None
        return next(
            (item for item in self.versions if item.version == self.current_version),
            None,
        )

    @model_validator(mode="after")
    def validate_state(self) -> RecurringServiceRecord:
        version_numbers = [item.version for item in self.versions]
        if len(version_numbers) != len(set(version_numbers)):
            raise ValueError("Recurring service versions must be unique.")
        if version_numbers != sorted(version_numbers):
            raise ValueError("Recurring service versions must be stored in ascending order.")
        if self.current_version is not None and self.active_version is None:
            raise ValueError("Current recurring service version does not exist.")
        if self.status is not RecurringServiceStatus.draft and self.active_version is None:
            raise ValueError("Recurring service status requires a current service version.")
        if self.status in {
            RecurringServiceStatus.offered,
            RecurringServiceStatus.active,
            RecurringServiceStatus.paused,
            RecurringServiceStatus.payment_blocked,
            RecurringServiceStatus.cancellation_pending,
            RecurringServiceStatus.cancelled,
            RecurringServiceStatus.expired,
        } and self.offered_at is None:
            raise ValueError("Offered and later recurring states require an offered-at timestamp.")
        if self.status in {
            RecurringServiceStatus.active,
            RecurringServiceStatus.paused,
            RecurringServiceStatus.payment_blocked,
            RecurringServiceStatus.cancellation_pending,
            RecurringServiceStatus.cancelled,
        }:
            if self.accepted_at is None or not self.acceptance_reference:
                raise ValueError("Active recurring service requires acceptance evidence.")
            if self.start_date is None:
                raise ValueError("Active recurring service requires a start date.")
        if self.status is RecurringServiceStatus.payment_blocked and not self.last_payment_state:
            raise ValueError("Payment-blocked service requires a payment-state reference.")
        if self.status is RecurringServiceStatus.paused and not self.pause_reference:
            raise ValueError("Paused service requires a pause reference.")
        if self.status in {
            RecurringServiceStatus.cancellation_pending,
            RecurringServiceStatus.cancelled,
        }:
            if self.cancellation_notice_date is None or not self.cancellation_reference:
                raise ValueError("Cancellation requires notice date and evidence/reference.")
        if self.status is RecurringServiceStatus.cancelled:
            if self.cancellation_effective_date is None:
                raise ValueError("Cancelled service requires an effective cancellation date.")
            if not self.exit_handoff_reference:
                raise ValueError("Cancelled service requires exit/handoff evidence.")
        return self


class RecurringServiceStoreError(RuntimeError):
    pass


class RecurringServiceStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, project_id: str) -> Path:
        return self.directory / f"{project_id}.json"

    def load(self, project_id: str) -> RecurringServiceRecord:
        try:
            text = self._path(project_id).read_text(encoding="utf-8")
            return RecurringServiceRecord.model_validate_json(text)
        except (OSError, ValueError) as exc:
            raise RecurringServiceStoreError(
                "Saved recurring service record was not found or is invalid."
            ) from exc

    def list(self) -> list[RecurringServiceRecord]:
        if not self.directory.exists():
            return []
        records: list[RecurringServiceRecord] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                records.append(RecurringServiceRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                raise RecurringServiceStoreError(
                    f"Saved recurring service record {path.name!r} is invalid."
                ) from exc
        return records

    def save(self, record: RecurringServiceRecord) -> None:
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
