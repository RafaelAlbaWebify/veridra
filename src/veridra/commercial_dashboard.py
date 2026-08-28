from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import TypeVar

from .customer_store import CustomerBillingStatus, CustomerRecord, CustomerStatus
from .lead_store import AuditLead, LeadStatus
from .prospect import Prospect, ProspectStatus

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CommercialSnapshot:
    prospect_counts: dict[ProspectStatus, int]
    lead_counts: dict[LeadStatus, int]
    customer_counts: dict[CustomerStatus, int]
    billing_counts: dict[CustomerBillingStatus, int]
    quoted_pipeline: dict[str, Decimal]
    expected_pipeline: dict[str, Decimal]
    invoiced_total: dict[str, Decimal]
    paid_total: dict[str, Decimal]
    overdue_total: dict[str, Decimal]

    @property
    def proposals(self) -> int:
        return self.prospect_counts.get(ProspectStatus.proposal, 0)

    @property
    def customers_onboarding(self) -> int:
        return self.customer_counts.get(CustomerStatus.onboarding, 0)

    @property
    def overdue_invoices(self) -> int:
        return self.billing_counts.get(CustomerBillingStatus.overdue, 0)


def _count(values: Iterable[T], members: Iterable[T]) -> dict[T, int]:
    counts = {item: 0 for item in members}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _add_money(target: dict[str, Decimal], currency: str, amount: Decimal | None) -> None:
    if amount is None:
        return
    target[currency] = target.get(currency, Decimal("0.00")) + amount


def build_commercial_snapshot(
    prospects: Iterable[Prospect],
    leads: Iterable[AuditLead],
    customers: Iterable[CustomerRecord],
) -> CommercialSnapshot:
    prospect_list = list(prospects)
    lead_list = list(leads)
    customer_list = list(customers)

    quoted_pipeline: dict[str, Decimal] = {}
    expected_pipeline: dict[str, Decimal] = {}
    for lead in lead_list:
        if lead.status not in {LeadStatus.won, LeadStatus.lost, LeadStatus.deleted_pending}:
            _add_money(quoted_pipeline, lead.currency, lead.quoted_value)
            _add_money(expected_pipeline, lead.currency, lead.expected_value)

    invoiced_total: dict[str, Decimal] = {}
    paid_total: dict[str, Decimal] = {}
    overdue_total: dict[str, Decimal] = {}
    for customer in customer_list:
        billing = customer.billing
        if billing.status in {
            CustomerBillingStatus.invoice_prepared,
            CustomerBillingStatus.invoice_sent,
            CustomerBillingStatus.paid,
            CustomerBillingStatus.overdue,
        }:
            _add_money(invoiced_total, billing.currency, billing.invoice_amount)
        if billing.status is CustomerBillingStatus.paid:
            _add_money(paid_total, billing.currency, billing.invoice_amount)
        if billing.status is CustomerBillingStatus.overdue:
            _add_money(overdue_total, billing.currency, billing.invoice_amount)

    return CommercialSnapshot(
        prospect_counts=_count((item.status for item in prospect_list), ProspectStatus),
        lead_counts=_count((item.status for item in lead_list), LeadStatus),
        customer_counts=_count((item.status for item in customer_list), CustomerStatus),
        billing_counts=_count(
            (item.billing.status for item in customer_list),
            CustomerBillingStatus,
        ),
        quoted_pipeline=quoted_pipeline,
        expected_pipeline=expected_pipeline,
        invoiced_total=invoiced_total,
        paid_total=paid_total,
        overdue_total=overdue_total,
    )
