from __future__ import annotations

import os
from pathlib import Path

from .atomic_fs_lock import AtomicFileLockError, exclusive_directory_lock
from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .profile_store import ProfileStore, ProfileStoreError
from .project_store import (
    ClientProject,
    ProjectEntry,
    ProjectStore,
    ProjectStoreError,
    project_id,
)


class TenantProjectStoreError(RuntimeError):
    pass


class TenantProjectCapacityError(TenantProjectStoreError):
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
    beneath that identity's tenant directory. Tenant project identifiers remain stable
    across mutable configuration updates so child assessments and tasks keep their
    project relationship.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> ProjectStore:
        return ProjectStore(self.root / identity.tenant_id / "projects")

    def _require_profile(self, identity: RequestIdentity, project: ClientProject) -> None:
        if project.profile_id is None:
            return
        try:
            ProfileStore(
                self.root / identity.tenant_id / "report-profiles"
            ).load(project.profile_id)
        except ProfileStoreError as exc:
            raise TenantProjectStoreError("Saved report profile was not found.") from exc

    @staticmethod
    def _target(identity: RequestIdentity, project_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="project",
            object_id=project_id,
        )

    def save(self, identity: RequestIdentity, project: ClientProject) -> str:
        require_tenant_capability(identity, TenantCapability.manage_projects)
        self._require_profile(identity, project)
        return self._store(identity).save(project)

    def save_with_capacity(
        self,
        identity: RequestIdentity,
        project: ClientProject,
        *,
        max_projects: int,
    ) -> str:
        if max_projects < 1:
            raise ValueError("Project capacity must be at least one.")
        require_tenant_capability(identity, TenantCapability.manage_projects)
        self._require_profile(identity, project)
        store = self._store(identity)
        lock_path = self.root / identity.tenant_id / ".project-capacity-lock"
        try:
            with exclusive_directory_lock(lock_path):
                entries = store.list()
                target_id = project_id(project)
                target_is_new = target_id not in {entry.id for entry in entries}
                if target_is_new and len(entries) >= max_projects:
                    raise TenantProjectCapacityError(
                        "The active plan project allowance is exhausted."
                    )
                return store.save(project)
        except AtomicFileLockError as exc:
            raise TenantProjectStoreError(
                "Project-capacity lock could not be acquired."
            ) from exc

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
        self._require_profile(identity, project)
        try:
            return self._store(identity).overwrite(target.object_id, project)
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
