from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .recurring_service import (
    RecurringServiceRecord,
    RecurringServiceStore,
    RecurringServiceStoreError,
)
from .tenant_project_store import default_tenant_data_directory


class TenantRecurringServiceStoreError(RuntimeError):
    pass


class TenantRecurringServiceStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> RecurringServiceStore:
        return RecurringServiceStore(
            self.root / identity.tenant_id / "recurring-services"
        )

    def load_or_empty(
        self,
        identity: RequestIdentity,
        project_id: str,
        customer_id: str,
    ) -> RecurringServiceRecord:
        require_tenant_capability(identity, TenantCapability.view_data)
        try:
            record = self._store(identity).load(project_id)
        except RecurringServiceStoreError:
            return RecurringServiceRecord(
                project_id=project_id,
                customer_id=customer_id,
            )
        if record.customer_id != customer_id:
            raise TenantRecurringServiceStoreError(
                "Recurring service customer linkage does not match the requested customer."
            )
        return record

    def list(self, identity: RequestIdentity) -> list[RecurringServiceRecord]:
        require_tenant_capability(identity, TenantCapability.view_data)
        try:
            return self._store(identity).list()
        except RecurringServiceStoreError as exc:
            raise TenantRecurringServiceStoreError(
                "Recurring service records could not be loaded safely."
            ) from exc

    def save(
        self,
        identity: RequestIdentity,
        record: RecurringServiceRecord,
    ) -> None:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        stamped = record.model_copy(update={"updated_at": datetime.now(UTC)})
        try:
            self._store(identity).save(stamped)
        except (OSError, ValueError) as exc:
            raise TenantRecurringServiceStoreError(
                "Recurring service record could not be saved safely."
            ) from exc
