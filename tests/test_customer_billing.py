from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from veridra.customer_lifecycle import upsert_customer_from_prospect
from veridra.customer_store import (
    CustomerAgreementState,
    CustomerBillingState,
    CustomerBillingStatus,
    CustomerOnboardingChecklist,
    CustomerRecord,
    CustomerSourceType,
    CustomerStatus,
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


def _accepted_agreement() -> CustomerAgreementState:
    return CustomerAgreementState(
        terms_reference="WEBIFY-MSA-001",
        terms_version="2026-09",
        accepted_at=datetime.now(UTC),
        acceptance_evidence="Synthetic acceptance email reference.",
        signature_reference="SIGN-SYNTHETIC-001",
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
    assert customer.booking_gate_required is False
    assert customer.work_may_start is True


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


def test_commercial_work_gate_requires_terms_before_work() -> None:
    customer = CustomerRecord(
        business_name="Booked Example Ltd",
        source_type=CustomerSourceType.prospect,
        source_id="e" * 24,
        booking_gate_required=True,
    )

    assert customer.work_may_start is False
    assert "accepted terms" in customer.booking_next_action.lower()

    accepted = customer.model_copy(update={"agreement": _accepted_agreement()})
    assert accepted.work_may_start is True
    assert accepted.booking_next_action == "Work may start. Continue onboarding and delivery."


def test_required_deposit_blocks_until_payment_evidence_satisfies_amount() -> None:
    customer = CustomerRecord(
        business_name="Deposit Example Ltd",
        source_type=CustomerSourceType.prospect,
        source_id="e" * 24,
        booking_gate_required=True,
        agreement=_accepted_agreement(),
        billing=CustomerBillingState(
            status=CustomerBillingStatus.invoice_sent,
            invoice_reference="WEB-2026-002",
            invoice_amount=Decimal("650.00"),
            deposit_required=True,
            deposit_amount=Decimal("325.00"),
        ),
    )
    assert customer.work_may_start is False
    assert "payment evidence" in customer.booking_next_action.lower()

    underpaid = customer.model_copy(
        update={
            "billing": CustomerBillingState(
                status=CustomerBillingStatus.partially_paid,
                invoice_reference="WEB-2026-002",
                invoice_amount=Decimal("650.00"),
                deposit_required=True,
                deposit_amount=Decimal("325.00"),
                amount_paid=Decimal("100.00"),
                payment_reference="PAY-SYNTHETIC-UNDER",
            )
        }
    )
    assert underpaid.work_may_start is False

    satisfied = customer.model_copy(
        update={
            "billing": CustomerBillingState(
                status=CustomerBillingStatus.partially_paid,
                invoice_reference="WEB-2026-002",
                invoice_amount=Decimal("650.00"),
                deposit_required=True,
                deposit_amount=Decimal("325.00"),
                amount_paid=Decimal("325.00"),
                payment_reference="PAY-SYNTHETIC-OK",
                payment_method_reference="bank transfer",
                payment_provider_reference="BANK-SYNTHETIC-001",
            )
        }
    )
    assert satisfied.work_may_start is True


def test_commercial_gate_rejects_kickoff_or_active_while_blocked() -> None:
    completed = CustomerOnboardingChecklist(
        contact_confirmed=True,
        scope_confirmed=True,
        commercial_terms_confirmed=True,
        access_requirements_confirmed=True,
        kickoff_completed=True,
    )
    base = CustomerRecord(
        business_name="Blocked Example Ltd",
        source_type=CustomerSourceType.prospect,
        source_id="f" * 24,
        booking_gate_required=True,
    )

    with pytest.raises(ValidationError):
        CustomerRecord.model_validate(
            {
                **base.model_dump(mode="json"),
                "onboarding": completed.model_dump(mode="json"),
            }
        )
    with pytest.raises(ValidationError):
        CustomerRecord.model_validate(
            {
                **base.model_dump(mode="json"),
                "status": CustomerStatus.active.value,
                "onboarding": completed.model_dump(mode="json"),
                "activated_at": datetime.now(UTC),
            }
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
    assert after.booking_gate_required is True
