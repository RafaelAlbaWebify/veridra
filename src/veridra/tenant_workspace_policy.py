from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .tenant_project_store import default_tenant_data_directory
from .workspace_policy import (
    PlanName,
    UsageEvent,
    UsageLedger,
    UsagePeriod,
    WorkspaceConfig,
    WorkspacePolicyError,
    WorkspaceStore,
)


class TenantWorkspacePolicyError(RuntimeError):
    pass


class WorkspacePlanChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_user_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    previous_plan: PlanName
    new_plan: PlanName
    changed_at: datetime


class TenantWorkspacePolicy:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _workspace_directory(self, tenant_id: str) -> Path:
        return self.root / tenant_id / "workspace"

    def workspace_store(self, identity: RequestIdentity) -> WorkspaceStore:
        return WorkspaceStore(self._workspace_directory(identity.tenant_id))

    def usage_ledger(self, identity: RequestIdentity) -> UsageLedger:
        return UsageLedger(self._workspace_directory(identity.tenant_id))

    def load(self, identity: RequestIdentity) -> WorkspaceConfig:
        require_tenant_capability(identity, TenantCapability.view_data)
        try:
            return self.workspace_store(identity).load()
        except WorkspacePolicyError as exc:
            raise TenantWorkspacePolicyError(
                "Tenant workspace configuration could not be read safely."
            ) from exc

    def save(self, identity: RequestIdentity, workspace: WorkspaceConfig) -> None:
        require_tenant_capability(identity, TenantCapability.manage_tenant)
        try:
            self.workspace_store(identity).save(workspace)
        except WorkspacePolicyError as exc:
            raise TenantWorkspacePolicyError(
                "Tenant workspace configuration could not be saved safely."
            ) from exc

    def record_usage(self, identity: RequestIdentity, event: UsageEvent) -> str:
        require_tenant_capability(identity, TenantCapability.view_data)
        try:
            return self.usage_ledger(identity).record(event)
        except WorkspacePolicyError as exc:
            raise TenantWorkspacePolicyError(
                "Tenant usage evidence could not be saved safely."
            ) from exc

    def list_usage(
        self,
        identity: RequestIdentity,
        *,
        period: UsagePeriod | None = None,
    ) -> list[tuple[str, UsageEvent]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self.usage_ledger(identity).list(period=period)

    def record_plan_change(
        self,
        identity: RequestIdentity,
        *,
        previous_plan: PlanName,
        new_plan: PlanName,
        changed_at: datetime | None = None,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.manage_tenant)
        event = WorkspacePlanChange(
            actor_user_id=identity.user_id,
            previous_plan=previous_plan,
            new_plan=new_plan,
            changed_at=(changed_at or datetime.now(UTC)).astimezone(UTC),
        )
        content = json.dumps(
            event.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        identifier = hashlib.sha256(content).hexdigest()[:24]
        destination = (
            self._workspace_directory(identity.tenant_id)
            / "plan-changes"
            / f"{identifier}.json"
        )
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(destination)
        return identifier

    def list_plan_changes(
        self,
        identity: RequestIdentity,
    ) -> list[tuple[str, WorkspacePlanChange]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        directory = self._workspace_directory(identity.tenant_id) / "plan-changes"
        if not directory.exists():
            return []
        events: list[tuple[str, WorkspacePlanChange]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                event = WorkspacePlanChange.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            events.append((path.stem, event))
        return sorted(events, key=lambda item: (item[1].changed_at, item[0]))
