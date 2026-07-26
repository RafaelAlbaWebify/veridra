from __future__ import annotations

from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .lead_store import LeadFormConfig, LeadFormStore, LeadStoreError
from .tenant_project_store import default_tenant_data_directory


class TenantLeadFormStoreError(RuntimeError):
    pass


class TenantLeadFormStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store_for_tenant(self, tenant_id: str) -> LeadFormStore:
        return LeadFormStore(self.root / tenant_id / "lead-forms")

    def _store(self, identity: RequestIdentity) -> LeadFormStore:
        return self._store_for_tenant(identity.tenant_id)

    @staticmethod
    def ref(identity: RequestIdentity, form_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="lead-form",
            object_id=form_id,
        )

    def save(self, identity: RequestIdentity, form: LeadFormConfig) -> str:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        return self._store(identity).save(form)

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> LeadFormConfig:
        require_tenant_scope(identity, target)
        if target.object_type != "lead-form":
            raise TenantLeadFormStoreError("Tenant object is not a lead-form reference.")
        try:
            return self._store(identity).load_form(target.object_id)
        except LeadStoreError as exc:
            raise TenantLeadFormStoreError("Saved lead form was not found.") from exc

    def load_public(self, *, tenant_id: str, form_id: str) -> LeadFormConfig:
        if len(tenant_id) != 24 or any(char not in "0123456789abcdef" for char in tenant_id):
            raise TenantLeadFormStoreError("Tenant identifier is invalid.")
        try:
            return self._store_for_tenant(tenant_id).load_form(form_id)
        except LeadStoreError as exc:
            raise TenantLeadFormStoreError("Saved lead form was not found.") from exc

    def list(self, identity: RequestIdentity) -> list[tuple[str, LeadFormConfig]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return [
            (form_id, LeadFormConfig.model_validate(model))
            for form_id, model in self._store(identity).list()
        ]

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        form: LeadFormConfig,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "lead-form":
            raise TenantLeadFormStoreError("Tenant object is not a lead-form reference.")
        try:
            return self._store(identity).replace(target.object_id, form)
        except LeadStoreError as exc:
            raise TenantLeadFormStoreError("Saved lead form was not found.") from exc

    def delete(self, identity: RequestIdentity, target: TenantObjectRef) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "lead-form":
            raise TenantLeadFormStoreError("Tenant object is not a lead-form reference.")
        try:
            self._store(identity).delete(target.object_id)
        except LeadStoreError as exc:
            raise TenantLeadFormStoreError("Saved lead form was not found.") from exc
