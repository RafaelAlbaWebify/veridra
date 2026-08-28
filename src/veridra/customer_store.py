from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_relationships(self) -> CustomerRecord:
        for project_id in self.project_ids:
            if len(project_id) != 24 or any(char not in "0123456789abcdef" for char in project_id):
                raise ValueError("Customer project identifiers must be 24 lowercase hex characters.")
        if self.status is CustomerStatus.active and not self.onboarding.complete:
            raise ValueError("Customer onboarding must be complete before activation.")
        return self


def customer_identifier(source_type: CustomerSourceType, source_id: str) -> str:
    canonical = f"{source_type.value}|{source_id}".encode("utf-8")
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
