from __future__ import annotations

from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .prospect import Prospect, ProspectStatus, ProspectStore, ProspectStoreError
from .tenant_project_store import default_tenant_data_directory


class TenantProspectStoreError(RuntimeError):
    pass


class TenantProspectStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> ProspectStore:
        return ProspectStore(self.root / identity.tenant_id / "prospects")

    @staticmethod
    def ref(identity: RequestIdentity, prospect_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="prospect",
            object_id=prospect_id,
        )

    def save(self, identity: RequestIdentity, prospect: Prospect) -> str:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        return self._store(identity).save(prospect)

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> Prospect:
        require_tenant_scope(identity, target)
        if target.object_type != "prospect":
            raise TenantProspectStoreError("Tenant object is not a prospect reference.")
        try:
            return self._store(identity).load(target.object_id)
        except ProspectStoreError as exc:
            raise TenantProspectStoreError("Saved prospect was not found.") from exc

    def list(
        self,
        identity: RequestIdentity,
        *,
        status: ProspectStatus | None = None,
    ) -> list[tuple[str, Prospect]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity).list(status=status)

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        prospect: Prospect,
    ) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "prospect":
            raise TenantProspectStoreError("Tenant object is not a prospect reference.")
        try:
            self._store(identity).replace(target.object_id, prospect)
        except ProspectStoreError as exc:
            raise TenantProspectStoreError("Saved prospect was not found.") from exc

    def delete(self, identity: RequestIdentity, target: TenantObjectRef) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "prospect":
            raise TenantProspectStoreError("Tenant object is not a prospect reference.")
        try:
            self._store(identity).delete(target.object_id)
        except ProspectStoreError as exc:
            raise TenantProspectStoreError("Saved prospect was not found.") from exc
