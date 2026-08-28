from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypeVar

from .customer_store import CustomerBillingStatus, CustomerRecord, CustomerStatus
from .lead_store import AuditLead, LeadStatus
from .prospect import Prospect, ProspectStatus

T = TypeVar("T")

_PROSPECT_TERMINAL = {
    ProspectStatus.customer,
    ProspectStatus.lost,
    ProspectStatus.unsuitable,
    ProspectStatus.duplicate,
    ProspectStatus.archived,
}
_LEAD_TERMINAL = {LeadStatus.won, LeadStatus.lost, LeadStatus.deleted_pending}
_OUTBOUND_FUNNEL = {
    ProspectStatus.contacted,
    ProspectStatus.responded,
    ProspectStatus.conversation,
    ProspectStatus.proposal,
    ProspectStatus.customer,
    ProspectStatus.lost,
}


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
    prospect_due_followups: int
    lead_due_followups: int
    project_count: int
    outbound_conversion_rate: Decimal
    inbound_win_rate: Decimal

    @property
    def proposals(self) -> int:
        return self.prospect_counts.get(ProspectStatus.proposal, 0)

    @property
    def customers_onboarding(self) -> int:
        return self.customer_counts.get(CustomerStatus.onboarding, 0)

    @property
    def overdue_invoices(self) -> int:
        return self.billing_counts.get(CustomerBillingStatus.overdue, 0)

    @property
    def due_followups(self) -> int:
        return self.prospect_due_followups + self.lead_due_followups


def _count(values: Iterable[T], members: Iterable[T]) -> dict[T, int]:
    counts = {item: 0 for item in members}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _add_money(target: dict[str, Decimal], currency: str, amount: Decimal | None) -> None:
    if amount is None:
        return
    target[currency] = target.get(currency, Decimal("0.00")) + amount


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_due(value: datetime | None, reference: datetime) -> bool:
    if value is None:
        return False
    return _normalise_datetime(value) <= _normalise_datetime(reference)


def _percentage(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.00")
    return (Decimal(numerator) * Decimal("100") / Decimal(denominator)).quantize(
        Decimal("0.01")
    )


def build_commercial_snapshot(
    prospects: Iterable[Prospect],
    leads: Iterable[AuditLead],
    customers: Iterable[CustomerRecord],
    *,
    projects: Iterable[object] = (),
    as_of: datetime | None = None,
) -> CommercialSnapshot:
    prospect_list = list(prospects)
    lead_list = list(leads)
    customer_list = list(customers)
    project_list = list(projects)
    reference = as_of or datetime.now(UTC)

    quoted_pipeline: dict[str, Decimal] = {}
    expected_pipeline: dict[str, Decimal] = {}
    for lead in lead_list:
        if lead.status not in _LEAD_TERMINAL:
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

    prospect_counts = _count((item.status for item in prospect_list), ProspectStatus)
    lead_counts = _count((item.status for item in lead_list), LeadStatus)
    outbound_entered = sum(prospect_counts.get(status, 0) for status in _OUTBOUND_FUNNEL)
    outbound_customers = prospect_counts.get(ProspectStatus.customer, 0)
    inbound_won = lead_counts.get(LeadStatus.won, 0)
    inbound_lost = lead_counts.get(LeadStatus.lost, 0)

    return CommercialSnapshot(
        prospect_counts=prospect_counts,
        lead_counts=lead_counts,
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
        prospect_due_followups=sum(
            1
            for item in prospect_list
            if item.status not in _PROSPECT_TERMINAL
            and _is_due(item.next_follow_up_at, reference)
        ),
        lead_due_followups=sum(
            1
            for item in lead_list
            if item.status not in _LEAD_TERMINAL and _is_due(item.next_follow_up_at, reference)
        ),
        project_count=len(project_list),
        outbound_conversion_rate=_percentage(outbound_customers, outbound_entered),
        inbound_win_rate=_percentage(inbound_won, inbound_won + inbound_lost),
    )
