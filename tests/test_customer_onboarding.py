from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError

from veridra.customer_lifecycle import upsert_customer_from_lead
from veridra.customer_store import (
    CustomerOnboardingChecklist,
    CustomerRecord,
    CustomerSourceType,
    CustomerStatus,
)
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.lead_store import AuditLead, LeadStatus
from veridra.prospect import Prospect, ProspectStatus
from veridra.tenant_customer_store import TenantCustomerStore
from veridra.tenant_prospect_store import TenantProspectStore


def _identity(tenant: str = "b") -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant * 24,
        membership_role=TenantRole.owner,
        session_id="c" * 24,
        authenticated_at=datetime.now(UTC),
    )


def test_no_website_outbound_customer_is_created_without_project(tmp_path: Path) -> None:
    identity = _identity()
    prospects = TenantProspectStore(tmp_path)
    prospect = Prospect(
        business_name="Daragh Example Dental",
        website=None,
        contact_name="Daragh Example",
        contact_email="daragh@example.ie",
        phone="01 555 0101",
        status=ProspectStatus.proposal,
        outreach_offer="Website Improvement Sprint",
        commercial_note="Website absence independently verified.",
    )
    prospect_id = prospects.save(identity, prospect)

    won = prospect.model_copy(update={"status": ProspectStatus.customer})
    prospects.replace(identity, prospects.ref(identity, prospect_id), won)

    customers = TenantCustomerStore(tmp_path).list(identity)
    assert len(customers) == 1
    customer_id, customer = customers[0]
    assert customer_id
    assert customer.source_type is CustomerSourceType.prospect
    assert customer.source_id == prospect_id
    assert customer.website is None
    assert customer.project_ids == ()
    assert customer.status is CustomerStatus.onboarding
    assert customer.booking_gate_required is True
    assert customer.work_may_start is False

    prospects.replace(identity, prospects.ref(identity, prospect_id), won)
    assert len(TenantCustomerStore(tmp_path).list(identity)) == 1


def test_customer_activation_requires_complete_onboarding() -> None:
    base = CustomerRecord(
        business_name="Example Ltd",
        source_type=CustomerSourceType.manual,
        source_id="d" * 24,
    )

    with pytest.raises(ValidationError):
        CustomerRecord.model_validate(
            {
                **base.model_dump(mode="json"),
                "status": CustomerStatus.active.value,
            }
        )

    checklist = CustomerOnboardingChecklist(
        contact_confirmed=True,
        scope_confirmed=True,
        commercial_terms_confirmed=True,
        access_requirements_confirmed=True,
        kickoff_completed=True,
    )
    active = CustomerRecord.model_validate(
        {
            **base.model_dump(mode="json"),
            "status": CustomerStatus.active.value,
            "onboarding": checklist.model_dump(mode="json"),
            "activated_at": datetime.now(UTC),
        }
    )
    assert active.status is CustomerStatus.active
    assert active.onboarding.complete is True
    assert active.booking_gate_required is False
    assert active.work_may_start is True


def test_won_inbound_lead_customer_keeps_project_and_commercial_value(tmp_path: Path) -> None:
    identity = _identity()
    lead = AuditLead(
        form_id="d" * 24,
        website=HttpUrl("https://example.com"),
        name="Alex Client",
        email="alex@example.com",
        company="Example Ltd",
        consent_text="I agree",
        consented_at=datetime.now(UTC),
        assessment_id="e" * 24,
        status=LeadStatus.won,
        offer_service="Website Improvement Sprint",
        quoted_value=Decimal("650.00"),
        currency="EUR",
    )

    customer_id = upsert_customer_from_lead(
        TenantCustomerStore(tmp_path),
        identity,
        lead_id="f" * 24,
        lead=lead,
        project_id="1" * 24,
    )
    customer = TenantCustomerStore(tmp_path).load(
        identity,
        TenantCustomerStore.ref(identity, customer_id),
    )

    assert customer.business_name == "Example Ltd"
    assert customer.project_ids == ("1" * 24,)
    assert customer.quoted_value == Decimal("650.00")
    assert customer.offer_service == "Website Improvement Sprint"
    assert customer.booking_gate_required is True
    assert customer.work_may_start is False


def test_customers_are_tenant_isolated(tmp_path: Path) -> None:
    owner = _identity("b")
    other = _identity("f")
    prospect = Prospect(business_name="Tenant A Client", status=ProspectStatus.proposal)
    prospect_id = TenantProspectStore(tmp_path).save(owner, prospect)
    TenantProspectStore(tmp_path).replace(
        owner,
        TenantProspectStore.ref(owner, prospect_id),
        prospect.model_copy(update={"status": ProspectStatus.customer}),
    )

    assert len(TenantCustomerStore(tmp_path).list(owner)) == 1
    assert TenantCustomerStore(tmp_path).list(other) == []
