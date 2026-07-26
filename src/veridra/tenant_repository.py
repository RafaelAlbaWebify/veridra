from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)


class TenantRepositoryError(RuntimeError):
    pass


class TenantRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    tenant_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    object_type: str = Field(min_length=1, max_length=80)
    object_id: str = Field(min_length=1, max_length=160)
    payload: dict[str, str] = Field(default_factory=dict)

    @property
    def reference(self) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=self.tenant_id,
            object_type=self.object_type,
            object_id=self.object_id,
        )


class TenantScopedRepository(Protocol):
    def load(self, identity: RequestIdentity, reference: TenantObjectRef) -> TenantRecord: ...

    def list_for_tenant(
        self,
        identity: RequestIdentity,
        object_type: str,
    ) -> list[TenantRecord]: ...

    def save(
        self,
        identity: RequestIdentity,
        record: TenantRecord,
        capability: TenantCapability,
    ) -> None: ...

    def delete(
        self,
        identity: RequestIdentity,
        reference: TenantObjectRef,
        capability: TenantCapability,
    ) -> None: ...


class InMemoryTenantRepository:
    """Reference implementation for contract tests, not production persistence."""

    def __init__(self, records: Iterable[TenantRecord] = ()) -> None:
        self._records = {
            (record.tenant_id, record.object_type, record.object_id): record
            for record in records
        }

    def load(self, identity: RequestIdentity, reference: TenantObjectRef) -> TenantRecord:
        require_tenant_scope(identity, reference)
        key = (reference.tenant_id, reference.object_type, reference.object_id)
        try:
            return self._records[key]
        except KeyError as exc:
            raise TenantRepositoryError("Tenant-scoped record was not found.") from exc

    def list_for_tenant(
        self,
        identity: RequestIdentity,
        object_type: str,
    ) -> list[TenantRecord]:
        return sorted(
            (
                record
                for record in self._records.values()
                if record.tenant_id == identity.tenant_id and record.object_type == object_type
            ),
            key=lambda record: record.object_id,
        )

    def save(
        self,
        identity: RequestIdentity,
        record: TenantRecord,
        capability: TenantCapability,
    ) -> None:
        require_tenant_capability(identity, capability)
        require_tenant_scope(identity, record.reference)
        key = (record.tenant_id, record.object_type, record.object_id)
        self._records[key] = record

    def delete(
        self,
        identity: RequestIdentity,
        reference: TenantObjectRef,
        capability: TenantCapability,
    ) -> None:
        require_tenant_capability(identity, capability)
        require_tenant_scope(identity, reference)
        key = (reference.tenant_id, reference.object_type, reference.object_id)
        if key not in self._records:
            raise TenantRepositoryError("Tenant-scoped record was not found.")
        del self._records[key]
