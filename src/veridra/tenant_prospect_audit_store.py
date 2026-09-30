from __future__ import annotations

from pathlib import Path

from .core import Assessment
from .history import HistoryEntry, HistoryError, HistoryStore
from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .tenant_project_store import default_tenant_data_directory
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError


class TenantProspectAuditStoreError(RuntimeError):
    pass


class TenantProspectAuditStore:
    """Persist public website assessments against a prospect, not a client project."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()
        self.prospects = TenantProspectStore(self.root)

    def _prospect(self, identity: RequestIdentity, prospect_id: str) -> None:
        try:
            self.prospects.load(identity, self.prospects.ref(identity, prospect_id))
        except TenantProspectStoreError as exc:
            raise TenantProspectAuditStoreError("Prospect was not found.") from exc

    def _store(self, identity: RequestIdentity, prospect_id: str) -> HistoryStore:
        self._prospect(identity, prospect_id)
        return HistoryStore(
            self.root / identity.tenant_id / "prospect-audits" / prospect_id
        )

    @staticmethod
    def ref(
        identity: RequestIdentity,
        prospect_id: str,
        assessment_id: str,
    ) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="prospect-assessment",
            object_id=f"{prospect_id}:{assessment_id}",
        )

    @staticmethod
    def _ids(target: TenantObjectRef) -> tuple[str, str]:
        if target.object_type != "prospect-assessment":
            raise TenantProspectAuditStoreError(
                "Tenant object is not a prospect assessment reference."
            )
        try:
            return tuple(target.object_id.split(":", 1))  # type: ignore[return-value]
        except ValueError as exc:
            raise TenantProspectAuditStoreError(
                "Prospect assessment reference is invalid."
            ) from exc

    def save(
        self,
        identity: RequestIdentity,
        prospect_id: str,
        assessment: Assessment,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.run_assessments)
        try:
            return self._store(identity, prospect_id).save(assessment)
        except HistoryError as exc:
            raise TenantProspectAuditStoreError(
                "Prospect assessment could not be saved."
            ) from exc

    def list(
        self,
        identity: RequestIdentity,
        prospect_id: str,
    ) -> list[HistoryEntry]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity, prospect_id).list()

    def load(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
    ) -> Assessment:
        require_tenant_capability(identity, TenantCapability.view_data)
        require_tenant_scope(identity, target)
        prospect_id, assessment_id = self._ids(target)
        try:
            return self._store(identity, prospect_id).load(assessment_id)
        except HistoryError as exc:
            raise TenantProspectAuditStoreError(
                "Prospect assessment was not found."
            ) from exc
