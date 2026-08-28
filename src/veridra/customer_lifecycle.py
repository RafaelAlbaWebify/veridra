from __future__ import annotations

from datetime import UTC, datetime

from .customer_store import (
    CustomerRecord,
    CustomerSourceType,
    customer_identifier,
)
from .identity_tenancy import RequestIdentity
from .lead_store import AuditLead
from .prospect import Prospect
from .tenant_customer_store import TenantCustomerStore, TenantCustomerStoreError


def _existing(
    store: TenantCustomerStore,
    identity: RequestIdentity,
    source_type: CustomerSourceType,
    source_id: str,
) -> tuple[str, CustomerRecord | None]:
    customer_id = customer_identifier(source_type, source_id)
    try:
        customer = store.load(identity, store.ref(identity, customer_id))
    except TenantCustomerStoreError:
        customer = None
    return customer_id, customer


def upsert_customer_from_lead(
    store: TenantCustomerStore,
    identity: RequestIdentity,
    *,
    lead_id: str,
    lead: AuditLead,
    project_id: str | None = None,
) -> str:
    customer_id, current = _existing(
        store,
        identity,
        CustomerSourceType.lead,
        lead_id,
    )
    projects = set(current.project_ids if current is not None else ())
    if project_id:
        projects.add(project_id)
    created_at = current.created_at if current is not None else datetime.now(UTC)
    customer = CustomerRecord(
        business_name=lead.company or lead.name,
        contact_name=lead.name,
        contact_email=str(lead.email),
        phone=lead.phone,
        website=lead.website,
        source_type=CustomerSourceType.lead,
        source_id=lead_id,
        project_ids=tuple(sorted(projects)),
        offer_service=lead.offer_service,
        quoted_value=lead.quoted_value,
        currency=lead.currency,
        commercial_notes=current.commercial_notes if current is not None else lead.notes,
        status=current.status if current is not None else "onboarding",
        onboarding=current.onboarding if current is not None else {},
        created_at=created_at,
        updated_at=datetime.now(UTC),
        activated_at=current.activated_at if current is not None else None,
    )
    saved_id = store.upsert(identity, customer)
    if saved_id != customer_id:
        raise TenantCustomerStoreError("Customer identity changed unexpectedly.")
    return saved_id


def upsert_customer_from_prospect(
    store: TenantCustomerStore,
    identity: RequestIdentity,
    *,
    prospect_id: str,
    prospect: Prospect,
) -> str:
    customer_id, current = _existing(
        store,
        identity,
        CustomerSourceType.prospect,
        prospect_id,
    )
    created_at = current.created_at if current is not None else datetime.now(UTC)
    customer = CustomerRecord(
        business_name=prospect.business_name,
        contact_name=prospect.contact_name,
        contact_email=prospect.contact_email,
        phone=prospect.phone,
        website=prospect.website,
        source_type=CustomerSourceType.prospect,
        source_id=prospect_id,
        project_ids=current.project_ids if current is not None else (),
        offer_service=prospect.outreach_offer or prospect.likely_offer,
        commercial_notes=(
            current.commercial_notes if current is not None else prospect.commercial_note
        ),
        status=current.status if current is not None else "onboarding",
        onboarding=current.onboarding if current is not None else {},
        created_at=created_at,
        updated_at=datetime.now(UTC),
        activated_at=current.activated_at if current is not None else None,
    )
    saved_id = store.upsert(identity, customer)
    if saved_id != customer_id:
        raise TenantCustomerStoreError("Customer identity changed unexpectedly.")
    return saved_id
