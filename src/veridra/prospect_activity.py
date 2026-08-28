from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import RequestIdentity, TenantCapability, require_tenant_capability


class ProspectActivityError(RuntimeError):
    pass


class ProspectActivityType(StrEnum):
    created = "created"
    stage_changed = "stage_changed"
    contact_recorded = "contact_recorded"
    follow_up_changed = "follow_up_changed"
    commercial_changed = "commercial_changed"
    note_changed = "note_changed"
    customer_converted = "customer_converted"


class ProspectActivityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurred_at: datetime
    event_type: ProspectActivityType
    summary: str = Field(min_length=1, max_length=500)
    actor: str = Field(default="", max_length=160)
    metadata: dict[str, str] = Field(default_factory=dict)


def _valid_identifier(value: str) -> bool:
    return len(value) == 24 and all(char in "0123456789abcdef" for char in value)


class TenantProspectActivityStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, tenant_id: str, prospect_id: str) -> Path:
        if not _valid_identifier(tenant_id):
            raise ProspectActivityError("Tenant identifier is invalid.")
        if not _valid_identifier(prospect_id):
            raise ProspectActivityError("Prospect identifier is invalid.")
        return self.root / tenant_id / "prospect-activity" / f"{prospect_id}.jsonl"

    @staticmethod
    def _event_bytes(event: ProspectActivityEvent) -> bytes:
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
        prospect_id: str,
        event_type: ProspectActivityType,
        summary: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> ProspectActivityEvent:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        event = ProspectActivityEvent(
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            summary=summary,
            actor=identity.user_id,
            metadata=metadata or {},
        )
        destination = self._path(identity.tenant_id, prospect_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("ab") as handle:
                handle.write(self._event_bytes(event))
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise ProspectActivityError("Prospect activity could not be appended safely.") from exc
        return event

    def ensure_created(self, identity: RequestIdentity, prospect_id: str) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        destination = self._path(identity.tenant_id, prospect_id)
        if destination.exists() and destination.stat().st_size > 0:
            return
        self.append(
            identity,
            prospect_id,
            ProspectActivityType.created,
            "Prospect record created",
        )

    def list(self, identity: RequestIdentity, prospect_id: str) -> list[ProspectActivityEvent]:
        require_tenant_capability(identity, TenantCapability.view_data)
        source = self._path(identity.tenant_id, prospect_id)
        if not source.exists():
            return []
        events: list[ProspectActivityEvent] = []
        try:
            for line in source.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(ProspectActivityEvent.model_validate_json(line))
        except (OSError, ValueError) as exc:
            raise ProspectActivityError("Prospect activity could not be read safely.") from exc
        return sorted(events, key=lambda event: event.occurred_at)
