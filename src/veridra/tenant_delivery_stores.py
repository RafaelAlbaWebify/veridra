from __future__ import annotations

from pathlib import Path

from .email_delivery import EmailAttemptStore
from .lead_delivery import LeadDeliveryStore
from .tenant_project_store import default_tenant_data_directory


class TenantDeliveryStoreError(RuntimeError):
    pass


def _validated_tenant_id(tenant_id: str) -> str:
    if len(tenant_id) != 24 or any(char not in "0123456789abcdef" for char in tenant_id):
        raise TenantDeliveryStoreError("Tenant identifier is invalid.")
    return tenant_id


class TenantDeliveryStores:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def webhook_attempts(self, tenant_id: str) -> LeadDeliveryStore:
        validated = _validated_tenant_id(tenant_id)
        return LeadDeliveryStore(self.root / validated / "lead-deliveries")

    def email_attempts(self, tenant_id: str) -> EmailAttemptStore:
        validated = _validated_tenant_id(tenant_id)
        return EmailAttemptStore(self.root / validated / "email-deliveries")
