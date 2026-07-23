# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class LeadStoreError(RuntimeError):
    pass


class LeadStatus(StrEnum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    won = "won"
    lost = "lost"
    deleted_pending = "deleted_pending"


class LeadFormConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organisation_label: str = Field(min_length=1, max_length=120)
    heading: str = Field(default="Get your free website report", min_length=1, max_length=160)
    introduction: str = Field(default="", max_length=1000)
    submit_label: str = Field(default="Get my report", min_length=1, max_length=80)
    consent_text: str = Field(min_length=1, max_length=1000)
    collect_company: bool = True
    collect_phone: bool = False
    allowed_origins: tuple[str, ...] = ()
    profile_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    webhook_url: str | None = Field(default=None, max_length=2048)
    webhook_secret: str | None = Field(default=None, min_length=16, max_length=256)
    notification_email: EmailStr | None = None
    cta_url: str | None = Field(default=None, max_length=2048)

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for value in values:
            parsed = HttpUrl(value)
            origin = f"{parsed.scheme}://{parsed.host}"
            port = parsed.port
            default_port = 443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else None
            if port is not None and port != default_port:
                origin += f":{port}"
            normalized.append(origin)
        return tuple(sorted(set(normalized)))

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = HttpUrl(value)
        if parsed.scheme != "https":
            raise ValueError("Lead webhook URL must use HTTPS.")
        return str(parsed)

    @field_validator("cta_url")
    @classmethod
    def validate_cta_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(HttpUrl(value))

    @model_validator(mode="after")
    def validate_webhook_pair(self) -> LeadFormConfig:
        if self.webhook_secret is not None and self.webhook_url is None:
            raise ValueError("A webhook secret requires a webhook URL.")
        return self


class AuditLead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    form_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    website: HttpUrl
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    company: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=80)
    consent_text: str = Field(min_length=1, max_length=1000)
    consented_at: datetime
    assessment_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    status: LeadStatus = LeadStatus.new
    notes: str = Field(default="", max_length=5000)
    assigned_owner: str = Field(default="", max_length=120)
    next_action: str = Field(default="", max_length=500)
    last_contacted_at: datetime | None = None
    next_follow_up_at: datetime | None = None


class LeadEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    form_id: str
    website: str
    name: str
    email: str
    status: LeadStatus
    consented_at: datetime
    assigned_owner: str = ""
    next_follow_up_at: datetime | None = None


def default_lead_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    root = Path(configured).expanduser().resolve() if configured else Path.home() / ".veridra"
    return root / "leads"


def _canonical_bytes(model: BaseModel) -> bytes:
    return json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def deterministic_id(model: BaseModel) -> str:
    return hashlib.sha256(_canonical_bytes(model)).hexdigest()[:24]


def consent_timestamp() -> datetime:
    return datetime.now(UTC)


class JsonModelStore:
    def __init__(self, directory: Path, model_type: type[BaseModel]) -> None:
        self.directory = directory
        self.model_type = model_type

    def _path(self, identifier: str) -> Path:
        valid = len(identifier) == 24 and all(char in "0123456789abcdef" for char in identifier)
        if not valid:
            raise LeadStoreError("Invalid lead data identifier.")
        return self.directory / f"{identifier}.json"

    def _write(self, destination: Path, model: BaseModel) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{destination.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(_canonical_bytes(model))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)

    def save(self, model: BaseModel) -> str:
        identifier = deterministic_id(model)
        destination = self._path(identifier)
        if not destination.exists():
            self._write(destination, model)
        return identifier

    def load(self, identifier: str) -> BaseModel:
        try:
            return self.model_type.model_validate_json(
                self._path(identifier).read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise LeadStoreError("Saved lead data was not found.") from exc
        except (OSError, ValueError) as exc:
            raise LeadStoreError("Saved lead data could not be read safely.") from exc

    def list(self) -> list[tuple[str, BaseModel]]:
        if not self.directory.exists():
            return []
        entries: list[tuple[str, BaseModel]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                model = self.model_type.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            entries.append((path.stem, model))
        return entries

    def replace(self, identifier: str, model: BaseModel) -> str:
        destination = self._path(identifier)
        if not destination.exists():
            raise LeadStoreError("Saved lead data was not found.")
        self._write(destination, model)
        return identifier

    def delete(self, identifier: str) -> None:
        try:
            self._path(identifier).unlink()
        except FileNotFoundError as exc:
            raise LeadStoreError("Saved lead data was not found.") from exc


class LeadFormStore(JsonModelStore):
    def __init__(self, directory: Path | None = None) -> None:
        super().__init__(directory or default_lead_directory() / "forms", LeadFormConfig)

    def load_form(self, identifier: str) -> LeadFormConfig:
        return LeadFormConfig.model_validate(super().load(identifier))


class LeadStore(JsonModelStore):
    def __init__(self, directory: Path | None = None) -> None:
        super().__init__(directory or default_lead_directory() / "records", AuditLead)

    def load_lead(self, identifier: str) -> AuditLead:
        return AuditLead.model_validate(super().load(identifier))

    def list_leads(
        self,
        *,
        form_id: str | None = None,
        status: LeadStatus | None = None,
        owner: str | None = None,
        follow_up_due_before: datetime | None = None,
    ) -> list[tuple[str, AuditLead]]:
        leads = [
            (identifier, AuditLead.model_validate(model))
            for identifier, model in super().list()
        ]
        return [
            item
            for item in leads
            if (form_id is None or item[1].form_id == form_id)
            and (status is None or item[1].status == status)
            and (owner is None or item[1].assigned_owner.casefold() == owner.casefold())
            and (
                follow_up_due_before is None
                or (
                    item[1].next_follow_up_at is not None
                    and item[1].next_follow_up_at <= follow_up_due_before
                )
            )
        ]
