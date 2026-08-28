# ruff: noqa: E501
from __future__ import annotations

import html
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .agency_navigation import agency_navigation
from .commercial_dashboard import build_commercial_snapshot
from .customer_store import CustomerBillingStatus, CustomerStatus
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .lead_store import LeadStatus
from .prospect import ProspectStatus
from .request_security import require_request_identity
from .tenant_customer_store import TenantCustomerStore
from .tenant_lead_store import TenantLeadStore
from .tenant_project_store import TenantProjectStore
from .tenant_prospect_store import TenantProspectStore

router = APIRouter(prefix="/agency/commercial", tags=["agency-commercial-dashboard"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1180px;margin:36px auto;padding:0 20px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{background:#fff;border:1px solid #dfe3e8;border-radius:9px;padding:18px}.metric{font-size:28px;font-weight:700;margin:6px 0}.muted{color:#68707a}.money{font-size:18px;font-weight:700;margin:5px 0}.actions{display:flex;gap:8px;flex-wrap:wrap}.button{display:inline-block;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none}.secondary{background:#59636e}.queue{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.queue{grid-template-columns:1fr 1fr}}@media(max-width:600px){.grid,.queue{grid-template-columns:1fr}}
"""


def _page(body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Commercial dashboard · Veridra</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _identity(request: Request) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.view_data)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    return identity


def _money(values: dict[str, Decimal]) -> str:
    if not values:
        return "—"
    return " · ".join(
        f"{html.escape(currency)} {html.escape(f'{amount:.2f}')}"
        for currency, amount in sorted(values.items())
    )


@router.get("", response_class=HTMLResponse)
def commercial_dashboard(request: Request) -> str:
    identity = _identity(request)
    root = _root(request)
    prospects = [prospect for _, prospect in TenantProspectStore(root).list(identity)]
    leads = [lead for _, lead in TenantLeadStore(root).list(identity)]
    customers = [customer for _, customer in TenantCustomerStore(root).list(identity)]
    projects = TenantProjectStore(root).list(identity)
    snapshot = build_commercial_snapshot(
        prospects,
        leads,
        customers,
        projects=projects,
    )

    active_pipeline = sum(
        snapshot.prospect_counts.get(status, 0)
        for status in (
            ProspectStatus.contacted,
            ProspectStatus.responded,
            ProspectStatus.conversation,
            ProspectStatus.proposal,
        )
    )
    open_inbound = sum(
        snapshot.lead_counts.get(status, 0)
        for status in (LeadStatus.new, LeadStatus.contacted, LeadStatus.qualified)
    )
    active_customers = snapshot.customer_counts.get(CustomerStatus.active, 0)
    paid_customers = snapshot.billing_counts.get(CustomerBillingStatus.paid, 0)

    body = f"""{agency_navigation(identity, current='commercial')}<section><h1>Commercial dashboard</h1><p class='muted'>Tenant-scoped view from prospecting through customer onboarding and cash collection. Currency totals are kept separate; no FX conversion or accounting treatment is applied.</p><div class='actions'><a class='button' href='/agency/prospects'>Prospects</a><a class='button secondary' href='/agency/leads'>Inbound leads</a><a class='button secondary' href='/agency/customers'>Customers</a><a class='button secondary' href='/agency/projects'>Client projects</a></div></section><section><div class='grid'><article class='card'><span class='muted'>Outbound sales in motion</span><div class='metric'>{active_pipeline}</div><span>contacted → proposal</span></article><article class='card'><span class='muted'>Open inbound leads</span><div class='metric'>{open_inbound}</div><span>new / contacted / qualified</span></article><article class='card'><span class='muted'>Active customers</span><div class='metric'>{active_customers}</div><span>onboarding completed</span></article><article class='card'><span class='muted'>Client projects</span><div class='metric'>{snapshot.project_count}</div><span>saved tenant projects</span></article></div></section><section><h2>Commercial KPIs</h2><div class='grid'><article class='card'><span class='muted'>Outbound customer conversion</span><div class='metric'>{snapshot.outbound_conversion_rate:.2f}%</div><span>customer ÷ prospects that entered sales funnel</span></article><article class='card'><span class='muted'>Inbound win rate</span><div class='metric'>{snapshot.inbound_win_rate:.2f}%</div><span>won ÷ decided inbound leads</span></article><article class='card'><span class='muted'>Due follow-ups</span><div class='metric'>{snapshot.due_followups}</div><span>{snapshot.prospect_due_followups} outbound · {snapshot.lead_due_followups} inbound</span></article><article class='card'><span class='muted'>Paid customers</span><div class='metric'>{paid_customers}</div><span>current billing record paid</span></article></div></section><section><h2>Pipeline value</h2><div class='grid'><article class='card'><span class='muted'>Inbound quoted pipeline</span><div class='money'>{_money(snapshot.quoted_pipeline)}</div></article><article class='card'><span class='muted'>Inbound expected pipeline</span><div class='money'>{_money(snapshot.expected_pipeline)}</div></article><article class='card'><span class='muted'>Client invoices tracked</span><div class='money'>{_money(snapshot.invoiced_total)}</div></article><article class='card'><span class='muted'>Paid</span><div class='money'>{_money(snapshot.paid_total)}</div></article></div></section><section><h2>Action queues</h2><div class='queue'><article class='card'><span class='muted'>Due outbound follow-ups</span><div class='metric'>{snapshot.prospect_due_followups}</div><a href='/agency/prospects'>Open prospects →</a></article><article class='card'><span class='muted'>Due inbound follow-ups</span><div class='metric'>{snapshot.lead_due_followups}</div><a href='/agency/leads'>Open leads →</a></article><article class='card'><span class='muted'>Customers still onboarding</span><div class='metric'>{snapshot.customers_onboarding}</div><a href='/agency/customers'>Open customers →</a></article><article class='card'><span class='muted'>Overdue invoices</span><div class='metric'>{snapshot.overdue_invoices}</div><div class='money'>{_money(snapshot.overdue_total)}</div><a href='/agency/customers'>Review billing →</a></article></div></section><section><h2>Stage detail</h2><div class='grid'><article class='card'><strong>Outbound prospects</strong><p>Contacted: {snapshot.prospect_counts.get(ProspectStatus.contacted, 0)}<br>Responded: {snapshot.prospect_counts.get(ProspectStatus.responded, 0)}<br>Conversation: {snapshot.prospect_counts.get(ProspectStatus.conversation, 0)}<br>Proposal: {snapshot.prospect_counts.get(ProspectStatus.proposal, 0)}<br>Customer: {snapshot.prospect_counts.get(ProspectStatus.customer, 0)}<br>Lost: {snapshot.prospect_counts.get(ProspectStatus.lost, 0)}</p></article><article class='card'><strong>Inbound leads</strong><p>New: {snapshot.lead_counts.get(LeadStatus.new, 0)}<br>Contacted: {snapshot.lead_counts.get(LeadStatus.contacted, 0)}<br>Qualified: {snapshot.lead_counts.get(LeadStatus.qualified, 0)}<br>Won: {snapshot.lead_counts.get(LeadStatus.won, 0)}<br>Lost: {snapshot.lead_counts.get(LeadStatus.lost, 0)}</p></article><article class='card'><strong>Customers</strong><p>Onboarding: {snapshot.customer_counts.get(CustomerStatus.onboarding, 0)}<br>Active: {snapshot.customer_counts.get(CustomerStatus.active, 0)}<br>Paused: {snapshot.customer_counts.get(CustomerStatus.paused, 0)}<br>Closed: {snapshot.customer_counts.get(CustomerStatus.closed, 0)}</p></article><article class='card'><strong>Billing</strong><p>Unbilled: {snapshot.billing_counts.get(CustomerBillingStatus.unbilled, 0)}<br>Prepared: {snapshot.billing_counts.get(CustomerBillingStatus.invoice_prepared, 0)}<br>Sent: {snapshot.billing_counts.get(CustomerBillingStatus.invoice_sent, 0)}<br>Paid: {snapshot.billing_counts.get(CustomerBillingStatus.paid, 0)}<br>Overdue: {snapshot.billing_counts.get(CustomerBillingStatus.overdue, 0)}<br>Cancelled: {snapshot.billing_counts.get(CustomerBillingStatus.cancelled, 0)}</p></article></div></section>"""
    return _page(body)
