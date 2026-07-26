from __future__ import annotations

from pathlib import Path

from .core import Assessment
from .history import Comparison, HistoryEntry, HistoryError, HistoryStore
from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError


class TenantHistoryStoreError(RuntimeError):
    pass


class TenantHistoryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.projects = TenantProjectStore(root)
        self.root = self.projects.root

    def _project(self, identity: RequestIdentity, project_id: str) -> None:
        try:
            self.projects.load(identity, self.projects.ref(identity, project_id))
        except TenantProjectStoreError as exc:
            raise TenantHistoryStoreError("Project was not found.") from exc

    def _store(self, identity: RequestIdentity, project_id: str) -> HistoryStore:
        self._project(identity, project_id)
        return HistoryStore(
            self.root
            / identity.tenant_id
            / "projects"
            / project_id
            / "assessments"
        )

    @staticmethod
    def ref(
        identity: RequestIdentity,
        project_id: str,
        assessment_id: str,
    ) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="project-assessment",
            object_id=f"{project_id}:{assessment_id}",
        )

    @staticmethod
    def _ids(target: TenantObjectRef) -> tuple[str, str]:
        if target.object_type != "project-assessment":
            raise TenantHistoryStoreError(
                "Tenant object is not a project assessment reference."
            )
        try:
            project_id, assessment_id = target.object_id.split(":", 1)
        except ValueError as exc:
            raise TenantHistoryStoreError(
                "Project assessment reference is invalid."
            ) from exc
        return project_id, assessment_id

    def save(
        self,
        identity: RequestIdentity,
        project_id: str,
        assessment: Assessment,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.run_assessments)
        try:
            return self._store(identity, project_id).save(assessment)
        except HistoryError as exc:
            raise TenantHistoryStoreError("Assessment could not be saved.") from exc

    def list(
        self,
        identity: RequestIdentity,
        project_id: str,
    ) -> list[HistoryEntry]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity, project_id).list()

    def load(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
    ) -> Assessment:
        require_tenant_capability(identity, TenantCapability.view_data)
        require_tenant_scope(identity, target)
        project_id, assessment_id = self._ids(target)
        try:
            return self._store(identity, project_id).load(assessment_id)
        except HistoryError as exc:
            raise TenantHistoryStoreError("Assessment was not found.") from exc

    def delete(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
    ) -> None:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        require_tenant_scope(identity, target)
        project_id, assessment_id = self._ids(target)
        try:
            self._store(identity, project_id).delete(assessment_id)
        except HistoryError as exc:
            raise TenantHistoryStoreError("Assessment was not found.") from exc

    def compare(
        self,
        identity: RequestIdentity,
        project_id: str,
        before_id: str,
        after_id: str,
    ) -> Comparison:
        require_tenant_capability(identity, TenantCapability.view_data)
        try:
            return self._store(identity, project_id).compare(before_id, after_id)
        except HistoryError as exc:
            raise TenantHistoryStoreError("Assessment was not found.") from exc
