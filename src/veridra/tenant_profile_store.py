from __future__ import annotations

from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .profile_store import ProfileEntry, ProfileStore, ProfileStoreError
from .report_profiles import ReportProfile
from .tenant_project_store import default_tenant_data_directory


class TenantProfileStoreError(RuntimeError):
    pass


class TenantProfileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> ProfileStore:
        return ProfileStore(self.root / identity.tenant_id / "report-profiles")

    @staticmethod
    def ref(identity: RequestIdentity, profile_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="report-profile",
            object_id=profile_id,
        )

    def save(self, identity: RequestIdentity, profile: ReportProfile) -> str:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        return self._store(identity).save(profile)

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> ReportProfile:
        require_tenant_capability(identity, TenantCapability.view_data)
        require_tenant_scope(identity, target)
        if target.object_type != "report-profile":
            raise TenantProfileStoreError("Tenant object is not a report profile reference.")
        try:
            return self._store(identity).load(target.object_id)
        except ProfileStoreError as exc:
            raise TenantProfileStoreError("Saved report profile was not found.") from exc

    def list(self, identity: RequestIdentity) -> list[ProfileEntry]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity).list()

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        profile: ReportProfile,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        require_tenant_scope(identity, target)
        if target.object_type != "report-profile":
            raise TenantProfileStoreError("Tenant object is not a report profile reference.")
        try:
            return self._store(identity).replace(target.object_id, profile)
        except ProfileStoreError as exc:
            raise TenantProfileStoreError("Saved report profile was not found.") from exc

    def update_in_place(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        profile: ReportProfile,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        require_tenant_scope(identity, target)
        if target.object_type != "report-profile":
            raise TenantProfileStoreError("Tenant object is not a report profile reference.")
        try:
            return self._store(identity).update_in_place(target.object_id, profile)
        except ProfileStoreError as exc:
            raise TenantProfileStoreError("Saved report profile was not found.") from exc

    def delete(self, identity: RequestIdentity, target: TenantObjectRef) -> None:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        require_tenant_scope(identity, target)
        if target.object_type != "report-profile":
            raise TenantProfileStoreError("Tenant object is not a report profile reference.")
        try:
            self._store(identity).delete(target.object_id)
        except ProfileStoreError as exc:
            raise TenantProfileStoreError("Saved report profile was not found.") from exc
