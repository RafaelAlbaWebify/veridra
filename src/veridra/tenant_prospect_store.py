from __future__ import annotations

from pathlib import Path

from .customer_lifecycle import upsert_customer_from_prospect
from .identity_tenancy import (
    RequestIdentity,
    TenantCapability,
    TenantObjectRef,
    require_tenant_capability,
    require_tenant_scope,
)
from .prospect import Prospect, ProspectStatus, ProspectStore, ProspectStoreError
from .prospect_activity import (
    ProspectActivityError,
    ProspectActivityType,
    TenantProspectActivityStore,
)
from .tenant_customer_store import TenantCustomerStore, TenantCustomerStoreError
from .tenant_project_store import default_tenant_data_directory


class TenantProspectStoreError(RuntimeError):
    pass


class TenantProspectStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_tenant_data_directory()

    def _store(self, identity: RequestIdentity) -> ProspectStore:
        return ProspectStore(self.root / identity.tenant_id / "prospects")

    def _activity(self) -> TenantProspectActivityStore:
        return TenantProspectActivityStore(self.root)

    @staticmethod
    def ref(identity: RequestIdentity, prospect_id: str) -> TenantObjectRef:
        return TenantObjectRef(
            tenant_id=identity.tenant_id,
            object_type="prospect",
            object_id=prospect_id,
        )

    def save(self, identity: RequestIdentity, prospect: Prospect) -> str:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        prospect_id = self._store(identity).save(prospect)
        try:
            self._activity().ensure_created(identity, prospect_id)
        except ProspectActivityError as exc:
            raise TenantProspectStoreError("Prospect activity could not be recorded.") from exc
        return prospect_id

    def load(self, identity: RequestIdentity, target: TenantObjectRef) -> Prospect:
        require_tenant_scope(identity, target)
        if target.object_type != "prospect":
            raise TenantProspectStoreError("Tenant object is not a prospect reference.")
        try:
            return self._store(identity).load(target.object_id)
        except ProspectStoreError as exc:
            raise TenantProspectStoreError("Saved prospect was not found.") from exc

    def list(
        self,
        identity: RequestIdentity,
        *,
        status: ProspectStatus | None = None,
    ) -> list[tuple[str, Prospect]]:
        require_tenant_capability(identity, TenantCapability.view_data)
        return self._store(identity).list(status=status)

    def replace(
        self,
        identity: RequestIdentity,
        target: TenantObjectRef,
        prospect: Prospect,
    ) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "prospect":
            raise TenantProspectStoreError("Tenant object is not a prospect reference.")
        try:
            previous = self._store(identity).load(target.object_id)
            self._store(identity).replace(target.object_id, prospect)
            activity = self._activity()
            activity.ensure_created(identity, target.object_id)
            if previous.status is not prospect.status:
                activity.append(
                    identity,
                    target.object_id,
                    ProspectActivityType.stage_changed,
                    f"Stage changed from {previous.status.value} to {prospect.status.value}",
                    metadata={
                        "from": previous.status.value,
                        "to": prospect.status.value,
                    },
                )
                if prospect.status is ProspectStatus.customer:
                    activity.append(
                        identity,
                        target.object_id,
                        ProspectActivityType.customer_converted,
                        "Prospect converted to customer",
                    )
            if previous.last_contacted_at != prospect.last_contacted_at:
                activity.append(
                    identity,
                    target.object_id,
                    ProspectActivityType.contact_recorded,
                    "Contact timestamp updated",
                )
            if (
                previous.next_follow_up_at != prospect.next_follow_up_at
                or previous.next_action != prospect.next_action
            ):
                activity.append(
                    identity,
                    target.object_id,
                    ProspectActivityType.follow_up_changed,
                    "Follow-up plan updated",
                )
            if (
                previous.outreach_offer != prospect.outreach_offer
                or previous.message_variant != prospect.message_variant
                or previous.commercial_loss_reason != prospect.commercial_loss_reason
            ):
                activity.append(
                    identity,
                    target.object_id,
                    ProspectActivityType.commercial_changed,
                    "Commercial details updated",
                )
            if previous.commercial_note != prospect.commercial_note:
                activity.append(
                    identity,
                    target.object_id,
                    ProspectActivityType.note_changed,
                    "Commercial note updated",
                )
            if prospect.status is ProspectStatus.customer:
                upsert_customer_from_prospect(
                    TenantCustomerStore(self.root),
                    identity,
                    prospect_id=target.object_id,
                    prospect=prospect,
                )
        except (ProspectStoreError, ProspectActivityError) as exc:
            raise TenantProspectStoreError("Saved prospect could not be updated safely.") from exc
        except TenantCustomerStoreError as exc:
            raise TenantProspectStoreError(
                "Customer onboarding record could not be saved."
            ) from exc

    def delete(self, identity: RequestIdentity, target: TenantObjectRef) -> None:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_scope(identity, target)
        if target.object_type != "prospect":
            raise TenantProspectStoreError("Tenant object is not a prospect reference.")
        try:
            self._store(identity).delete(target.object_id)
        except ProspectStoreError as exc:
            raise TenantProspectStoreError("Saved prospect was not found.") from exc
