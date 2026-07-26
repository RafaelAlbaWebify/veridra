from __future__ import annotations

from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .lead_store import AuditLead, LeadStatus, LeadStore, LeadStoreError
from .tenant_project_store import default_tenant_data_directory


class TenantLeadStoreError(RuntimeError):
    pass


class TenantLeadStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store_for_tenant(self, tenant_id: str) -> LeadStore:
        return LeadStore(self.root / tenant_id / "leads")

    def _store(self, identity: RequestIdentity) -> LeadStore:
        return self._store_for_tenant(identity.tenant_id)

    @staticmethod
    def ref(identity: RequestIdentity, lead_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="lead",
            object_id=lead_id,
        )

    def save(self, identity: RequestIdentity, lead: AuditLead) -> str:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        return self._store(identity).save(lead)

    def save_bound_public_capture(self, *, tenant_id: str, lead: AuditLead) -> str:
        """Persist a public lead only after server-side form-to-tenant resolution."""
        if len(tenant_id) != 24 or any(char not in "0123456789abcdef" for char in tenant_id):
            raise TenantLeadStoreError("Tenant identifier is invalid.")
        return self._store_for_tenant(tenant_id).save(lead)

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> AuditLead:
        require_tenant_scope(identity, target)
        if target.object_type != "lead":
            raise TenantLeadStoreError("Tenant object is not a lead reference.")
        try:
            return self._store(identity).load_lead(target.object_id)
        except LeadStoreError as exc:
            raise TenantLeadStoreError("Saved lead was not found.") from exc

    def list(
        self,
        identity: RequestIdentity,
        *,
        status: LeadStatus | None = None,
    ) -> list[tuple[str, AuditLead]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity).list_leads(status=status)

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        lead: AuditLead,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "lead":
            raise TenantLeadStoreError("Tenant object is not a lead reference.")
        try:
            return self._store(identity).replace(target.object_id, lead)
        except LeadStoreError as exc:
            raise TenantLeadStoreError("Saved lead was not found.") from exc

    def delete(self, identity: RequestIdentity, target: TenantObjectRef) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "lead":
            raise TenantLeadStoreError("Tenant object is not a lead reference.")
        try:
            self._store(identity).delete(target.object_id)
        except LeadStoreError as exc:
            raise TenantLeadStoreError("Saved lead was not found.") from exc
