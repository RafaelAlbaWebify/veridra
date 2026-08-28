from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from veridra.customer_lifecycle import upsert_customer_from_prospect
from veridra.customer_store import (
    CustomerBillingState,
    CustomerBillingStatus,
    CustomerRecord,
    CustomerSourceType,
)
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.prospect import Prospect, ProspectStatus
from veridra.tenant_customer_store import TenantCustomerStore


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id="b" * 24,
        membership_role=TenantRole.owner,
        session_id="c" * 24,
        authenticated_at=datetime.now(UTC),
    )


def test_new_customer_defaults_to_unbilled() -> None:
    customer = CustomerRecord(
        business_name="Example Ltd",
        source_type=CustomerSourceType.manual,
        source_id="d" * 24,
    )

    assert customer.billing.status is CustomerBillingStatus.unbilled
    assert customer.billing.invoice_reference == ""
    assert customer.billing.invoice_amount is None
    assert customer.billing.paid_at is None


def test_invoiced_states_require_reference_and_amount() -> None:
    with pytest.raises(ValidationError):
        CustomerBillingState(status=CustomerBillingStatus.invoice_sent)

    invoice = CustomerBillingState(
        status=CustomerBillingStatus.invoice_sent,
        invoice_reference="WEB-2026-001",
        invoice_amount=Decimal("650.00"),
        issued_on=date(2026, 8, 28),
        due_on=date(2026, 9, 11),
    )

    assert invoice.invoice_reference == "WEB-2026-001"
    assert invoice.invoice_amount == Decimal("650.00")


def test_paid_state_requires_payment_timestamp() -> None:
    with pytest.raises(ValidationError):
        CustomerBillingState(
            status=CustomerBillingStatus.paid,
            invoice_reference="WEB-2026-001",
            invoice_amount=Decimal("650.00"),
        )

    paid_at = datetime.now(UTC)
    paid = CustomerBillingState(
        status=CustomerBillingStatus.paid,
        invoice_reference="WEB-2026-001",
        invoice_amount=Decimal("650.00"),
        paid_at=paid_at,
    )
    assert paid.paid_at == paid_at


def test_due_date_cannot_precede_issue_date() -> None:
    with pytest.raises(ValidationError):
        CustomerBillingState(
            status=CustomerBillingStatus.invoice_prepared,
            invoice_reference="WEB-2026-001",
            invoice_amount=Decimal("650.00"),
            issued_on=date(2026, 8, 28),
            due_on=date(2026, 8, 27),
        )


def test_prospect_refresh_preserves_existing_billing_state(tmp_path: Path) -> None:
    identity = _identity()
    store = TenantCustomerStore(tmp_path)
    prospect = Prospect(
        business_name="No Site Dental",
        website=None,
        status=ProspectStatus.customer,
        outreach_offer="Website Improvement Sprint",
    )
    prospect_id = "e" * 24
    customer_id = upsert_customer_from_prospect(
        store,
        identity,
        prospect_id=prospect_id,
        prospect=prospect,
    )
    customer = store.load(identity, store.ref(identity, customer_id))
    billing = CustomerBillingState(
        status=CustomerBillingStatus.invoice_sent,
        invoice_reference="WEB-2026-001",
        invoice_amount=Decimal("650.00"),
        currency="EUR",
        issued_on=date(2026, 8, 28),
        due_on=date(2026, 9, 11),
        note="Sent by email.",
    )
    store.replace(
        identity,
        store.ref(identity, customer_id),
        customer.model_copy(update={"billing": billing}),
    )

    refreshed = prospect.model_copy(update={"commercial_note": "Customer replied."})
    upsert_customer_from_prospect(
        store,
        identity,
        prospect_id=prospect_id,
        prospect=refreshed,
    )
    after = store.load(identity, store.ref(identity, customer_id))

    assert after.billing == billing
