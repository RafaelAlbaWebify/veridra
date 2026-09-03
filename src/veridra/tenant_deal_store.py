from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .deal_lifecycle import DealRecord, DealStore, DealStoreError
from .identity_tenancy import RequestIdentity, TenantCapability, require_tenant_capability
from .tenant_project_store import default_tenant_data_directory


class TenantDealStoreError(RuntimeError):
    pass


class TenantDealStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> DealStore:
        return DealStore(self.root / identity.tenant_id / "deals")

    def load_or_empty(self, identity: RequestIdentity, prospect_id: str) -> DealRecord:
        require_tenant_capability(identity, TenantCapability.view_data)
        try:
            return self._store(identity).load(prospect_id)
        except DealStoreError:
            return DealRecord(prospect_id=prospect_id)

    def save(self, identity: RequestIdentity, record: DealRecord) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        stamped = record.model_copy(update={"updated_at": datetime.now(UTC)})
        try:
            self._store(identity).save(stamped)
        except (OSError, ValueError) as exc:
            raise TenantDealStoreError("Deal record could not be saved safely.") from exc
