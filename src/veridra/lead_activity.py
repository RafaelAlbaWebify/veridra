from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)


class LeadActivityError(RuntimeError):
    pass


class LeadActivityType(StrEnum):
    created = "created"
    stage_changed = "stage_changed"
    contact_recorded = "contact_recorded"
    follow_up_changed = "follow_up_changed"
    commercial_changed = "commercial_changed"
    note_changed = "note_changed"
    project_converted = "project_converted"


class LeadActivityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurred_at: datetime
    event_type: LeadActivityType
    summary: str = Field(min_length=1, max_length=500)
    actor: str = Field(default="", max_length=160)
    metadata: dict[str, str] = Field(default_factory=dict)


def _valid_identifier(value: str) -> bool:
    return len(value) == 24 and all(char in "0123456789abcdef" for char in value)


class TenantLeadActivityStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _directory(self, tenant_id: str) -> Path:
        if not _valid_identifier(tenant_id):
            raise LeadActivityError("Tenant identifier is invalid.")
        return self.root / tenant_id / "lead-activity"

    def _path(self, tenant_id: str, lead_id: str) -> Path:
        if not _valid_identifier(lead_id):
            raise LeadActivityError("Lead identifier is invalid.")
        return self._directory(tenant_id) / f"{lead_id}.jsonl"

    @staticmethod
    def _event_bytes(event: LeadActivityEvent) -> bytes:
        payload = json.dumps(
            event.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return (payload + "\n").encode("utf-8")

    def append(
        self,
        identity: RequestIdentity,
        lead_id: str,
        event_type: LeadActivityType,
        summary: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> LeadActivityEvent:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        event = LeadActivityEvent(
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            summary=summary,
            actor=identity.user_id,
            metadata=metadata or {},
        )
        destination = self._path(identity.tenant_id, lead_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("ab") as handle:
                handle.write(self._event_bytes(event))
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise LeadActivityError("Lead activity could not be appended safely.") from exc
        return event

    def ensure_created(self, identity: RequestIdentity, lead_id: str) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        destination = self._path(identity.tenant_id, lead_id)
        if destination.exists() and destination.stat().st_size > 0:
            return
        self.append(identity, lead_id, LeadActivityType.created, "Lead record created")

    def list(self, identity: RequestIdentity, lead_id: str) -> list[LeadActivityEvent]:
        require_tenant_capability(identity, TenantCapability.view_data)
        source = self._path(identity.tenant_id, lead_id)
        if not source.exists():
            return []
        events: list[LeadActivityEvent] = []
        try:
            for line in source.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(LeadActivityEvent.model_validate_json(line))
        except (OSError, ValueError) as exc:
            raise LeadActivityError("Lead activity could not be read safely.") from exc
        return sorted(events, key=lambda event: event.occurred_at)

    def save_snapshot(self, identity: RequestIdentity, lead_id: str) -> Path:
        """Write an atomic JSON snapshot without changing the append-only event log."""
        events = self.list(identity, lead_id)
        directory = self._directory(identity.tenant_id)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{lead_id}.snapshot.json"
        payload = json.dumps(
            [event.model_dump(mode="json") for event in events],
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8")
        with NamedTemporaryFile(mode="wb", dir=directory, delete=False) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return destination
