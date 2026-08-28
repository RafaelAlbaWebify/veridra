from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from veridra.commercial_dashboard import build_commercial_snapshot
from veridra.customer_store import (
    CustomerBillingState,
    CustomerBillingStatus,
    CustomerOnboardingChecklist,
    CustomerStatus,
)
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect, ProspectStatus
from veridra.tenant_customer_store import TenantCustomerStore
from veridra.tenant_prospect_store import TenantProspectStore


def _identity(tenant: str, user: str) -> RequestIdentity:
    return RequestIdentity(
        user_id=user * 24,
        tenant_id=tenant * 24,
        membership_role=TenantRole.owner,
        session_id="f" * 24,
        authenticated_at=datetime.now(UTC),
    )


def test_no_site_prospect_can_become_onboarded_paid_customer(tmp_path: Path) -> None:
    identity = _identity("a", "b")
    other_tenant = _identity("c", "d")
    prospects = TenantProspectStore(tmp_path)
    customers = TenantCustomerStore(tmp_path)

    prospect = Prospect(
        business_name="First Customer Dental",
        website=None,
        contact_name="Practice Owner",
        contact_email="owner@example.com",
        phone="+353 1 555 0100",
        locality="Dublin",
        country_code="IE",
        status=ProspectStatus.proposal,
        outreach_offer="Website Improvement Sprint",
        commercial_note="Proposal discussed with decision maker.",
        human_verified=True,
    )
    prospect_id = prospects.save(identity, prospect)

    won = prospect.model_copy(
        update={
            "status": ProspectStatus.customer,
            "commercial_note": "Accepted Website Improvement Sprint.",
            "updated_at": datetime.now(UTC),
        }
    )
    prospects.replace(identity, prospects.ref(identity, prospect_id), won)

    customer_entries = customers.list(identity)
    assert len(customer_entries) == 1
    customer_id, customer = customer_entries[0]
    assert customer.website is None
    assert customer.status is CustomerStatus.onboarding
    assert customer.project_ids == ()
    assert customer.offer_service == "Website Improvement Sprint"
    assert customers.list(other_tenant) == []

    # Replaying the won/customer source transition must not create a duplicate.
    prospects.replace(identity, prospects.ref(identity, prospect_id), won)
    assert len(customers.list(identity)) == 1

    completed = CustomerOnboardingChecklist(
        contact_confirmed=True,
        scope_confirmed=True,
        commercial_terms_confirmed=True,
        access_requirements_confirmed=True,
        kickoff_completed=True,
    )
    paid_at = datetime.now(UTC)
    paid = customer.model_copy(
        update={
            "status": CustomerStatus.active,
            "onboarding": completed,
            "billing": CustomerBillingState(
                status=CustomerBillingStatus.paid,
                invoice_reference="WEB-2026-001",
                invoice_amount=Decimal("650.00"),
                currency="EUR",
                paid_at=paid_at,
                note="Synthetic acceptance payment.",
            ),
            "activated_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
    )
    customers.replace(identity, customers.ref(identity, customer_id), paid)

    # A later source refresh must preserve onboarding, active state and payment history.
    refreshed_prospect = won.model_copy(
        update={
            "commercial_note": "Post-sale source note refreshed.",
            "updated_at": datetime.now(UTC),
        }
    )
    prospects.replace(
        identity,
        prospects.ref(identity, prospect_id),
        refreshed_prospect,
    )
    after_refresh = customers.load(identity, customers.ref(identity, customer_id))

    assert after_refresh.status is CustomerStatus.active
    assert after_refresh.onboarding.complete is True
    assert after_refresh.billing.status is CustomerBillingStatus.paid
    assert after_refresh.billing.invoice_reference == "WEB-2026-001"
    assert after_refresh.billing.invoice_amount == Decimal("650.00")
    assert after_refresh.billing.paid_at == paid_at
    assert after_refresh.website is None
    assert after_refresh.project_ids == ()

    snapshot = build_commercial_snapshot(
        [refreshed_prospect],
        [],
        [after_refresh],
    )
    assert snapshot.customer_counts[CustomerStatus.active] == 1
    assert snapshot.billing_counts[CustomerBillingStatus.paid] == 1
    assert snapshot.paid_total == {"EUR": Decimal("650.00")}
    assert snapshot.overdue_total == {}
