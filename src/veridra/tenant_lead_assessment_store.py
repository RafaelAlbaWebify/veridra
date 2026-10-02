from __future__ import annotations

from pathlib import Path

from .core import Assessment
from .history import HistoryError, HistoryStore
from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .tenant_project_store import default_tenant_data_directory


class TenantLeadAssessmentStoreError(RuntimeError):
    pass


class TenantLeadAssessmentStore:
    """Persist public lead assessments inside the owning tenant durable root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    @staticmethod
    def _tenant_id(value: str) -> str:
        tenant_id = value.strip().lower()
        if len(tenant_id) != 24 or any(
            char not in "0123456789abcdef" for char in tenant_id
        ):
            raise TenantLeadAssessmentStoreError("Tenant identifier is invalid.")
        return tenant_id

    def _store(self, tenant_id: str) -> HistoryStore:
        return HistoryStore(
            self.root / self._tenant_id(tenant_id) / "lead-assessments"
        )

    def save_bound_public_capture(
        self,
        *,
        tenant_id: str,
        assessment: Assessment,
    ) -> str:
        try:
            return self._store(tenant_id).save(assessment)
        except HistoryError as exc:
            raise TenantLeadAssessmentStoreError(
                "Lead assessment could not be saved."
            ) from exc

    def load(
        self,
        identity: RequestIdentity,
        assessment_id: str,
    ) -> Assessment:
        require_tenant_capability(identity, TenantCapability.view_data)
        try:
            return self._store(identity.tenant_id).load(assessment_id)
        except HistoryError as exc:
            raise TenantLeadAssessmentStoreError(
                "Lead assessment was not found."
            ) from exc
