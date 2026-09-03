from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class CustomerStoreError(RuntimeError):
    pass


class CustomerSourceType(StrEnum):
    lead = "lead"
    prospect = "prospect"
    manual = "manual"


class CustomerStatus(StrEnum):
    onboarding = "onboarding"
    active = "active"
    paused = "paused"
    closed = "closed"


class CustomerBillingStatus(StrEnum):
    unbilled = "unbilled"
    reference_pending = "reference_pending"
    invoice_prepared = "invoice_prepared"
    issued = "issued"
    invoice_sent = "invoice_sent"
    due = "due"
    partially_paid = "partially_paid"
    paid = "paid"
    overdue = "overdue"
    cancelled = "cancelled"
    refunded = "refunded"


class CustomerOnboardingChecklist(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contact_confirmed: bool = False
    scope_confirmed: bool = False
    commercial_terms_confirmed: bool = False
    access_requirements_confirmed: bool = False
    kickoff_completed: bool = False

    @property
    def complete(self) -> bool:
        return all(
            (
                self.contact_confirmed,
                self.scope_confirmed,
                self.commercial_terms_confirmed,
                self.access_requirements_confirmed,
                self.kickoff_completed,
            )
        )


class CustomerAgreementState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    terms_reference: str = Field(default="", max_length=240)
    terms_version: str = Field(default="", max_length=80)
    accepted_at: datetime | None = None
    acceptance_evidence: str = Field(default="", max_length=2000)
    signature_reference: str = Field(default="", max_length=240)

    @property
    def accepted(self) -> bool:
        return bool(
            self.terms_reference
            and self.terms_version
            and self.accepted_at is not None
            and self.acceptance_evidence
        )

    @model_validator(mode="after")
    def validate_acceptance(self) -> CustomerAgreementState:
        acceptance_started = bool(
            self.accepted_at is not None
            or self.acceptance_evidence
            or self.signature_reference
        )
        if acceptance_started and not (
            self.terms_reference and self.terms_version and self.accepted_at is not None
        ):
            raise ValueError(
                "Accepted terms require a terms reference, version and accepted-at timestamp."
            )
        if self.accepted_at is not None and not self.acceptance_evidence:
            raise ValueError("Accepted terms require acceptance evidence.")
        return self


class CustomerBillingState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    status: CustomerBillingStatus = CustomerBillingStatus.unbilled
    invoice_reference: str = Field(default="", max_length=120)
    invoice_external_url: HttpUrl | None = None
    invoice_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    issued_on: date | None = None
    due_on: date | None = None
    deposit_required: bool = False
    deposit_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    amount_paid: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    payment_reference: str = Field(default="", max_length=240)
    payment_method_reference: str = Field(default="", max_length=160)
    payment_provider_reference: str = Field(default="", max_length=240)
    paid_at: datetime | None = None
    note: str = Field(default="", max_length=2000)

    @property
    def payment_evidence_recorded(self) -> bool:
        return bool(
            self.payment_reference
            and self.amount_paid is not None
            and self.amount_paid > Decimal("0")
        )

    @property
    def required_upfront_payment_satisfied(self) -> bool:
        if not self.deposit_required:
            return True
        if self.deposit_amount is None or self.deposit_amount <= Decimal("0"):
            return False
        return bool(
            self.invoice_reference
            and self.payment_evidence_recorded
            and self.amount_paid is not None
            and self.amount_paid >= self.deposit_amount
            and self.status
            in {
                CustomerBillingStatus.partially_paid,
                CustomerBillingStatus.paid,
            }
        )

    @model_validator(mode="after")
    def validate_billing_state(self) -> CustomerBillingState:
        if (
            self.issued_on is not None
            and self.due_on is not None
            and self.due_on < self.issued_on
        ):
            raise ValueError("Invoice due date cannot be before the issue date.")
        invoiced_states = {
            CustomerBillingStatus.invoice_prepared,
            CustomerBillingStatus.issued,
            CustomerBillingStatus.invoice_sent,
            CustomerBillingStatus.due,
            CustomerBillingStatus.partially_paid,
            CustomerBillingStatus.paid,
            CustomerBillingStatus.overdue,
            CustomerBillingStatus.cancelled,
            CustomerBillingStatus.refunded,
        }
        if self.status in invoiced_states:
            if not self.invoice_reference:
                raise ValueError("Invoiced billing states require an invoice reference.")
            if self.invoice_amount is None:
                raise ValueError("Invoiced billing states require an invoice amount.")
        if self.deposit_required and (
            self.deposit_amount is None or self.deposit_amount <= Decimal("0")
        ):
            raise ValueError("A required deposit must have a positive required amount.")
        if self.status is CustomerBillingStatus.partially_paid:
            if not self.payment_evidence_recorded:
                raise ValueError("Partially paid billing requires payment evidence.")
        if self.status is CustomerBillingStatus.paid and self.paid_at is None:
            raise ValueError("Paid billing state requires a payment timestamp.")
        return self


class CustomerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    business_name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(default="", max_length=160)
    contact_email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=80)
    website: HttpUrl | None = None
    source_type: CustomerSourceType
    source_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    project_ids: tuple[str, ...] = ()
    offer_service: str = Field(default="", max_length=240)
    quoted_value: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    commercial_notes: str = Field(default="", max_length=5000)
    status: CustomerStatus = CustomerStatus.onboarding
    onboarding: CustomerOnboardingChecklist = Field(default_factory=CustomerOnboardingChecklist)
    agreement: CustomerAgreementState = Field(default_factory=CustomerAgreementState)
    billing: CustomerBillingState = Field(default_factory=CustomerBillingState)
    booking_gate_required: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None

    @property
    def work_may_start(self) -> bool:
        if not self.booking_gate_required:
            return True
        return bool(
            self.agreement.accepted and self.billing.required_upfront_payment_satisfied
        )

    @property
    def booking_next_action(self) -> str:
        if not self.booking_gate_required:
            return "Commercial booking gate is not required for this record."
        if not self.agreement.accepted:
            return "Capture accepted terms and acceptance evidence before work starts."
        if self.billing.deposit_required and not self.billing.required_upfront_payment_satisfied:
            if not self.billing.invoice_reference:
                return "Capture the external invoice reference before requesting the deposit."
            return "Waiting for required payment evidence before work starts."
        return "Work may start. Continue onboarding and delivery."

    @model_validator(mode="after")
    def validate_relationships(self) -> CustomerRecord:
        for project_id in self.project_ids:
            invalid = len(project_id) != 24 or any(
                char not in "0123456789abcdef" for char in project_id
            )
            if invalid:
                raise ValueError(
                    "Customer project identifiers must be 24 lowercase hex characters."
                )
        if self.status is CustomerStatus.active and not self.onboarding.complete:
            raise ValueError("Customer onboarding must be complete before activation.")
        if self.booking_gate_required and not self.work_may_start:
            if self.onboarding.kickoff_completed:
                raise ValueError(
                    "Kickoff cannot be completed until accepted terms and required payment evidence are recorded."
                )
            if self.status is CustomerStatus.active:
                raise ValueError(
                    "Customer cannot become active until the commercial work-start gate is open."
                )
        return self


def customer_identifier(source_type: CustomerSourceType, source_id: str) -> str:
    canonical = f"{source_type.value}|{source_id}".encode()
    return hashlib.sha256(canonical).hexdigest()[:24]


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


class CustomerStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, customer_id: str) -> Path:
        valid = len(customer_id) == 24 and all(
            character in "0123456789abcdef" for character in customer_id
        )
        if not valid:
            raise CustomerStoreError("Invalid customer identifier.")
        return self.directory / f"{customer_id}.json"

    @staticmethod
    def _bytes(customer: CustomerRecord) -> bytes:
        return json.dumps(
            customer.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def save(self, customer: CustomerRecord) -> str:
        customer_id = customer_identifier(customer.source_type, customer.source_id)
        destination = self._path(customer_id)
        if destination.exists():
            raise CustomerStoreError("Customer record already exists.")
        _atomic_write(destination, self._bytes(customer))
        return customer_id

    def upsert(self, customer: CustomerRecord) -> str:
        customer_id = customer_identifier(customer.source_type, customer.source_id)
        _atomic_write(self._path(customer_id), self._bytes(customer))
        return customer_id

    def load(self, customer_id: str) -> CustomerRecord:
        try:
            return CustomerRecord.model_validate_json(
                self._path(customer_id).read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise CustomerStoreError("Saved customer was not found or is invalid.") from exc

    def list(self) -> list[tuple[str, CustomerRecord]]:
        if not self.directory.exists():
            return []
        entries: list[tuple[str, CustomerRecord]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                customer = CustomerRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            entries.append((path.stem, customer))
        return sorted(entries, key=lambda item: (item[1].updated_at, item[0]), reverse=True)

    def replace(self, customer_id: str, customer: CustomerRecord) -> None:
        destination = self._path(customer_id)
        if not destination.exists():
            raise CustomerStoreError("Saved customer was not found.")
        expected = customer_identifier(customer.source_type, customer.source_id)
        if expected != customer_id:
            raise CustomerStoreError("Customer source identity cannot be changed in place.")
        _atomic_write(destination, self._bytes(customer))