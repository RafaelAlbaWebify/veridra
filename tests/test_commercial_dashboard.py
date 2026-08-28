from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import HttpUrl

from veridra.commercial_dashboard import build_commercial_snapshot
from veridra.customer_store import (
    CustomerBillingState,
    CustomerBillingStatus,
    CustomerRecord,
    CustomerSourceType,
    CustomerStatus,
)
from veridra.lead_store import AuditLead, LeadStatus
from veridra.prospect import Prospect, ProspectStatus


def _lead(
    *,
    status: LeadStatus,
    currency: str,
    quoted: Decimal | None,
    expected: Decimal | None,
) -> AuditLead:
    return AuditLead(
        form_id="a" * 24,
        website=HttpUrl("https://example.com"),
        name="Example Lead",
        email="lead@example.com",
        consent_text="I agree",
        consented_at=datetime.now(UTC),
        assessment_id="b" * 24,
        status=status,
        quoted_value=quoted,
        expected_value=expected,
        currency=currency,
    )


def _customer(
    source_id: str,
    *,
    status: CustomerStatus,
    billing_status: CustomerBillingStatus,
    amount: Decimal | None,
    currency: str,
) -> CustomerRecord:
    paid_at = datetime.now(UTC) if billing_status is CustomerBillingStatus.paid else None
    reference = "WEB-001" if billing_status not in {
        CustomerBillingStatus.unbilled,
        CustomerBillingStatus.cancelled,
    } else ""
    return CustomerRecord(
        business_name=f"Customer {source_id[0]}",
        source_type=CustomerSourceType.manual,
        source_id=source_id,
        status=status,
        billing=CustomerBillingState(
            status=billing_status,
            invoice_reference=reference,
            invoice_amount=amount,
            currency=currency,
            paid_at=paid_at,
        ),
    )


def test_empty_commercial_snapshot_is_safe() -> None:
    snapshot = build_commercial_snapshot([], [], [])

    assert snapshot.proposals == 0
    assert snapshot.customers_onboarding == 0
    assert snapshot.overdue_invoices == 0
    assert snapshot.quoted_pipeline == {}
    assert snapshot.paid_total == {}


def test_pipeline_and_cash_totals_keep_currencies_separate() -> None:
    leads = [
        _lead(
            status=LeadStatus.qualified,
            currency="EUR",
            quoted=Decimal("650.00"),
            expected=Decimal("500.00"),
        ),
        _lead(
            status=LeadStatus.contacted,
            currency="GBP",
            quoted=Decimal("400.00"),
            expected=Decimal("200.00"),
        ),
        _lead(
            status=LeadStatus.won,
            currency="EUR",
            quoted=Decimal("900.00"),
            expected=Decimal("900.00"),
        ),
    ]
    customers = [
        _customer(
            "c" * 24,
            status=CustomerStatus.active,
            billing_status=CustomerBillingStatus.paid,
            amount=Decimal("650.00"),
            currency="EUR",
        ),
        _customer(
            "d" * 24,
            status=CustomerStatus.onboarding,
            billing_status=CustomerBillingStatus.overdue,
            amount=Decimal("300.00"),
            currency="EUR",
        ),
        _customer(
            "e" * 24,
            status=CustomerStatus.active,
            billing_status=CustomerBillingStatus.invoice_sent,
            amount=Decimal("450.00"),
            currency="GBP",
        ),
    ]
    prospects = [
        Prospect(business_name="Proposal", status=ProspectStatus.proposal),
        Prospect(business_name="Conversation", status=ProspectStatus.conversation),
    ]

    snapshot = build_commercial_snapshot(prospects, leads, customers)

    assert snapshot.proposals == 1
    assert snapshot.customers_onboarding == 1
    assert snapshot.overdue_invoices == 1
    assert snapshot.quoted_pipeline == {
        "EUR": Decimal("650.00"),
        "GBP": Decimal("400.00"),
    }
    assert snapshot.expected_pipeline == {
        "EUR": Decimal("500.00"),
        "GBP": Decimal("200.00"),
    }
    assert snapshot.invoiced_total == {
        "EUR": Decimal("950.00"),
        "GBP": Decimal("450.00"),
    }
    assert snapshot.paid_total == {"EUR": Decimal("650.00")}
    assert snapshot.overdue_total == {"EUR": Decimal("300.00")}
