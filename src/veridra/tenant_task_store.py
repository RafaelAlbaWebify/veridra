from __future__ import annotations

from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .task_store import RemediationTask, TaskStatus, TaskStore, TaskStoreError
from .tenant_project_store import default_tenant_data_directory


class TenantTaskStoreError(RuntimeError):
    pass


class TenantTaskStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> TaskStore:
        return TaskStore(self.root / identity.tenant_id / "tasks")

    @staticmethod
    def ref(identity: RequestIdentity, task_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="task",
            object_id=task_id,
        )

    def save(self, identity: RequestIdentity, task: RemediationTask) -> str:
        require_tenant_capability(identity, TenantCapability.manage_tasks)
        return self._store(identity).save(task)

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> RemediationTask:
        require_tenant_scope(identity, target)
        if target.object_type != "task":
            raise TenantTaskStoreError("Tenant object is not a task reference.")
        try:
            return self._store(identity).load(target.object_id)
        except TaskStoreError as exc:
            raise TenantTaskStoreError("Saved remediation task was not found.") from exc

    def list(
        self,
        identity: RequestIdentity,
        *,
        project_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[tuple[str, RemediationTask]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity).list(project_id=project_id, status=status)

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        task: RemediationTask,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.manage_tasks)
        require_tenant_scope(identity, target)
        if target.object_type != "task":
            raise TenantTaskStoreError("Tenant object is not a task reference.")
        try:
            return self._store(identity).replace(target.object_id, task)
        except TaskStoreError as exc:
            raise TenantTaskStoreError("Saved remediation task was not found.") from exc

    def delete(self, identity: RequestIdentity, target: TenantObjectRef) -> None:
        require_tenant_capability(identity, TenantCapability.manage_tasks)
        require_tenant_scope(identity, target)
        if target.object_type != "task":
            raise TenantTaskStoreError("Tenant object is not a task reference.")
        try:
            self._store(identity).delete(target.object_id)
        except TaskStoreError as exc:
            raise TenantTaskStoreError("Saved remediation task was not found.") from exc
