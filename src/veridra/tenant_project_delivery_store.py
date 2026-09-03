from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .project_delivery import (
    ProjectDeliveryRecord,
    ProjectDeliveryStore,
    ProjectDeliveryStoreError,
)
from .tenant_project_store import default_tenant_data_directory


class TenantProjectDeliveryStoreError(RuntimeError):
    pass


class TenantProjectDeliveryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> ProjectDeliveryStore:
        return ProjectDeliveryStore(
            self.root / identity.tenant_id / "project-delivery"
        )

    def load_or_empty(
        self,
        identity: RequestIdentity,
        project_id: str,
    ) -> ProjectDeliveryRecord:
        require_tenant_capability(identity, TenantCapability.view_data)
        try:
            return self._store(identity).load(project_id)
        except ProjectDeliveryStoreError:
            return ProjectDeliveryRecord(project_id=project_id)

    def save(
        self,
        identity: RequestIdentity,
        record: ProjectDeliveryRecord,
    ) -> None:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        stamped = record.model_copy(update={"updated_at": datetime.now(UTC)})
        try:
            self._store(identity).save(stamped)
        except (OSError, ValueError) as exc:
            raise TenantProjectDeliveryStoreError(
                "Project delivery record could not be saved safely."
            ) from exc
