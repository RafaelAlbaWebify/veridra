from __future__ import annotations

import os
from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .project_store import ClientProject, ProjectEntry, ProjectStore, ProjectStoreError


class TenantProjectStoreError(RuntimeError):
    pass


def default_tenant_data_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve() / "tenants"
    return Path.home() / ".veridra" / "tenants"


class TenantProjectStore:
    """Tenant-qualified local JSON project persistence.

    This is a migration-compatible local persistence step, not a production database.
    Every public operation requires a verified request identity and resolves storage
    beneath that identity's tenant directory.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> ProjectStore:
        return ProjectStore(self.root / identity.tenant_id / "projects")

    @staticmethod
    def _target(identity: RequestIdentity, project_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="project",
            object_id=project_id,
        )

    def save(self, identity: RequestIdentity, project: ClientProject) -> str:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        return self._store(identity).save(project)

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> ClientProject:
        require_tenant_scope(identity, target)
        if target.object_type != "project":
            raise TenantProjectStoreError("Tenant object is not a project reference.")
        try:
            return self._store(identity).load(target.object_id)
        except ProjectStoreError as exc:
            raise TenantProjectStoreError("Saved project was not found.") from exc

    def list(self, identity: RequestIdentity) -> list[ProjectEntry]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity).list()

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        project: ClientProject,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        require_tenant_scope(identity, target)
        if target.object_type != "project":
            raise TenantProjectStoreError("Tenant object is not a project reference.")
        try:
            return self._store(identity).replace(target.object_id, project)
        except ProjectStoreError as exc:
            raise TenantProjectStoreError("Saved project was not found.") from exc

    def delete(self, identity: RequestIdentity, target: TenantObjectRef) -> None:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        require_tenant_scope(identity, target)
        if target.object_type != "project":
            raise TenantProjectStoreError("Tenant object is not a project reference.")
        try:
            self._store(identity).delete(target.object_id)
        except ProjectStoreError as exc:
            raise TenantProjectStoreError("Saved project was not found.") from exc

    def ref(self, identity: RequestIdentity, project_id: str) -> TenantObjectRef:
        return self._target(identity, project_id)
