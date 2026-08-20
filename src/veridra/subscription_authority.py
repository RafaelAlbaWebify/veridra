from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .tenant_project_store import default_tenant_data_directory
from .workspace_policy import PlanName, WorkspaceConfig, WorkspaceStatus, WorkspaceStore

_TENANT_ID = re.compile(r"^[0-9a-f]{24}$")


class SubscriptionAuthorityError(RuntimeError):
    pass


class SubscriptionUpdate(BaseModel):
    """Provider-neutral subscription state that may authoritatively drive entitlements."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    provider: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    provider_event_id: str = Field(min_length=1, max_length=160)
    external_subscription_id: str = Field(min_length=1, max_length=160)
    plan: PlanName
    status: WorkspaceStatus
    cycle_anchor_day: int = Field(ge=1, le=28)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Subscription event timestamps must include a timezone.")
        return value.astimezone(UTC)


class AppliedSubscriptionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    update: SubscriptionUpdate
    previous_workspace: WorkspaceConfig
    projected_workspace: WorkspaceConfig
    applied_at: datetime


class SubscriptionApplyResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_key: str
    applied: bool
    workspace: WorkspaceConfig


def _atomic_json(path: Path, payload: BaseModel) -> None:
    content = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
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


def _event_key(update: SubscriptionUpdate) -> str:
    identity = f"{update.provider}\0{update.provider_event_id}".encode()
    return hashlib.sha256(identity).hexdigest()[:24]


class SubscriptionAuthority:
    """Apply trusted billing-provider state to an existing tenant workspace.

    The authority is intentionally not an HTTP endpoint. Provider adapters or controlled
    operational tooling may call it after authenticating and validating provider events.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _workspace_directory(self, tenant_id: str) -> Path:
        if _TENANT_ID.fullmatch(tenant_id) is None:
            raise SubscriptionAuthorityError("Tenant identifier is invalid.")
        return self.root / tenant_id / "workspace"

    def _events_directory(self, tenant_id: str) -> Path:
        return self._workspace_directory(tenant_id) / "subscription-events"

    def _event_path(self, update: SubscriptionUpdate) -> Path:
        return self._events_directory(update.tenant_id) / f"{_event_key(update)}.json"

    def list_events(self, tenant_id: str) -> list[AppliedSubscriptionEvent]:
        directory = self._events_directory(tenant_id)
        if not directory.exists():
            return []
        events: list[AppliedSubscriptionEvent] = []
        for path in sorted(directory.glob("*.json")):
            try:
                event = AppliedSubscriptionEvent.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            events.append(event)
        return sorted(
            events,
            key=lambda event: (
                event.update.occurred_at,
                event.update.provider,
                event.update.provider_event_id,
            ),
        )

    def apply(
        self,
        update: SubscriptionUpdate,
        *,
        applied_at: datetime | None = None,
    ) -> SubscriptionApplyResult:
        event_path = self._event_path(update)
        event_key = event_path.stem
        if event_path.exists():
            try:
                existing = AppliedSubscriptionEvent.model_validate_json(
                    event_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise SubscriptionAuthorityError(
                    "Existing subscription event evidence could not be read safely."
                ) from exc
            if existing.update != update:
                raise SubscriptionAuthorityError(
                    "Provider event identity was reused with different subscription data."
                )
            return SubscriptionApplyResult(
                event_key=event_key,
                applied=False,
                workspace=existing.projected_workspace,
            )

        events = self.list_events(update.tenant_id)
        if events:
            latest = events[-1].update
            if update.occurred_at < latest.occurred_at:
                raise SubscriptionAuthorityError(
                    "Stale subscription event cannot replace newer entitlement state."
                )
            if update.occurred_at == latest.occurred_at:
                raise SubscriptionAuthorityError(
                    "Ambiguous subscription events share the same provider timestamp."
                )

        workspace_store = WorkspaceStore(self._workspace_directory(update.tenant_id))
        workspace_existed = workspace_store.path.exists()
        previous = workspace_store.load()
        projected = previous.model_copy(
            update={
                "plan": update.plan,
                "status": update.status,
                "cycle_anchor_day": update.cycle_anchor_day,
            }
        )
        applied_timestamp = applied_at or datetime.now(UTC)
        if applied_timestamp.tzinfo is None or applied_timestamp.utcoffset() is None:
            raise SubscriptionAuthorityError("Applied timestamp must include a timezone.")
        event = AppliedSubscriptionEvent(
            update=update,
            previous_workspace=previous,
            projected_workspace=projected,
            applied_at=applied_timestamp.astimezone(UTC),
        )

        try:
            workspace_store.save(projected)
            _atomic_json(event_path, event)
        except Exception as exc:
            try:
                if workspace_existed:
                    workspace_store.save(previous)
                else:
                    workspace_store.path.unlink(missing_ok=True)
            except Exception as rollback_exc:
                raise SubscriptionAuthorityError(
                    "Subscription projection failed and workspace rollback also failed."
                ) from rollback_exc
            raise SubscriptionAuthorityError(
                "Subscription event could not be projected safely."
            ) from exc

        return SubscriptionApplyResult(
            event_key=event_key,
            applied=True,
            workspace=projected,
        )
