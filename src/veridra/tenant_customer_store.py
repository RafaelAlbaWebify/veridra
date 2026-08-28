from __future__ import annotations

from pathlib import Path

from .customer_store import CustomerRecord, CustomerStore, CustomerStoreError
from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .tenant_project_store import default_tenant_data_directory


class TenantCustomerStoreError(RuntimeError):
    pass


class TenantCustomerStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> CustomerStore:
        return CustomerStore(self.root / identity.tenant_id / "customers")

    @staticmethod
    def ref(identity: RequestIdentity, customer_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="customer",
            object_id=customer_id,
        )

    def upsert(self, identity: RequestIdentity, customer: CustomerRecord) -> str:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        try:
            return self._store(identity).upsert(customer)
        except CustomerStoreError as exc:
            raise TenantCustomerStoreError("Customer record could not be saved.") from exc

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> CustomerRecord:
        require_tenant_scope(identity, target)
        if target.object_type != "customer":
            raise TenantCustomerStoreError("Tenant object is not a customer reference.")
        try:
            return self._store(identity).load(target.object_id)
        except CustomerStoreError as exc:
            raise TenantCustomerStoreError("Saved customer was not found.") from exc

    def list(self, identity: RequestIdentity) -> list[tuple[str, CustomerRecord]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity).list()

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        customer: CustomerRecord,
    ) -> None:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        require_tenant_scope(identity, target)
        if target.object_type != "customer":
            raise TenantCustomerStoreError("Tenant object is not a customer reference.")
        try:
            self._store(identity).replace(target.object_id, customer)
        except CustomerStoreError as exc:
            raise TenantCustomerStoreError("Saved customer could not be updated.") from exc
