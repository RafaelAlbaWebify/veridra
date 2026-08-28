from __future__ import annotations

from pathlib import Path

from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .lead_activity import (
    LeadActivityError,
    LeadActivityType,
    TenantLeadActivityStore,
)
from .lead_store import AuditLead, LeadStatus, LeadStore, LeadStoreError
from .tenant_project_store import default_tenant_data_directory


class TenantLeadStoreError(RuntimeError):
    pass


class TenantLeadStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store_for_tenant(self, tenant_id: str) -> LeadStore:
        return LeadStore(self.root / tenant_id / "leads")

    def _store(self, identity: RequestIdentity) -> LeadStore:
        return self._store_for_tenant(identity.tenant_id)

    def _activity(self) -> TenantLeadActivityStore:
        return TenantLeadActivityStore(self.root)

    @staticmethod
    def ref(identity: RequestIdentity, lead_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="lead",
            object_id=lead_id,
        )

    def save(self, identity: RequestIdentity, lead: AuditLead) -> str:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        lead_id = self._store(identity).save(lead)
        try:
            self._activity().ensure_created(identity, lead_id)
        except LeadActivityError as exc:
            raise TenantLeadStoreError("Lead activity could not be recorded.") from exc
        return lead_id

    def save_bound_public_capture(self, *, tenant_id: str, lead: AuditLead) -> str:
        """Persist a public lead only after server-side form-to-tenant resolution."""
        if len(tenant_id) != 24 or any(char not in "0123456789abcdef" for char in tenant_id):
            raise TenantLeadStoreError("Tenant identifier is invalid.")
        return self._store_for_tenant(tenant_id).save(lead)

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> AuditLead:
        require_tenant_scope(identity, target)
        if target.object_type != "lead":
            raise TenantLeadStoreError("Tenant object is not a lead reference.")
        try:
            return self._store(identity).load_lead(target.object_id)
        except LeadStoreError as exc:
            raise TenantLeadStoreError("Saved lead was not found.") from exc

    def list(
        self,
        identity: RequestIdentity,
        *,
        status: LeadStatus | None = None,
    ) -> list[tuple[str, AuditLead]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity).list_leads(status=status)

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        lead: AuditLead,
    ) -> str:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "lead":
            raise TenantLeadStoreError("Tenant object is not a lead reference.")
        try:
            previous = self._store(identity).load_lead(target.object_id)
            result = self._store(identity).replace(target.object_id, lead)
            activity = self._activity()
            activity.ensure_created(identity, target.object_id)
            if previous.status != lead.status:
                activity.append(
                    identity,
                    target.object_id,
                    LeadActivityType.stage_changed,
                    f"Stage changed from {previous.status.value} to {lead.status.value}",
                    metadata={"from": previous.status.value, "to": lead.status.value},
                )
            if previous.last_contacted_at != lead.last_contacted_at:
                activity.append(
                    identity,
                    target.object_id,
                    LeadActivityType.contact_recorded,
                    "Contact timestamp updated",
                )
            if (
                previous.next_follow_up_at != lead.next_follow_up_at
                or previous.next_action != lead.next_action
            ):
                activity.append(
                    identity,
                    target.object_id,
                    LeadActivityType.follow_up_changed,
                    "Follow-up plan updated",
                )
            if (
                previous.offer_service != lead.offer_service
                or previous.quoted_value != lead.quoted_value
                or previous.expected_value != lead.expected_value
                or previous.currency != lead.currency
                or previous.loss_reason != lead.loss_reason
            ):
                activity.append(
                    identity,
                    target.object_id,
                    LeadActivityType.commercial_changed,
                    "Commercial details updated",
                )
            if previous.notes != lead.notes:
                activity.append(
                    identity,
                    target.object_id,
                    LeadActivityType.note_changed,
                    "Lead notes updated",
                )
            return result
        except (LeadStoreError, LeadActivityError) as exc:
            raise TenantLeadStoreError("Saved lead could not be updated safely.") from exc

    def delete(self, identity: RequestIdentity, target: TenantObjectRef) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "lead":
            raise TenantLeadStoreError("Tenant object is not a lead reference.")
        try:
            self._store(identity).delete(target.object_id)
        except LeadStoreError as exc:
            raise TenantLeadStoreError("Saved lead was not found.") from exc
