# ruff: noqa: E501
from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .agency_navigation import agency_navigation
from .customer_store import CustomerOnboardingChecklist, CustomerRecord, CustomerStatus
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .request_security import require_request_identity
from .tenant_customer_store import TenantCustomerStore, TenantCustomerStoreError

router = APIRouter(prefix="/agency/customers", tags=["agency-customers"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1100px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.card{border:1px solid #dfe3e8;border-radius:9px;padding:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:110px}.check{display:flex;gap:9px;align-items:center;margin:12px 0}.check input{width:auto}.actions{display:flex;gap:8px;flex-wrap:wrap}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}@media(max-width:760px){.cards,.row{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _identity(request: Request, *, manage: bool = False) -> RequestIdentity:
    identity = require_request_identity(request)
    capability = TenantCapability.manage_projects if manage else TenantCapability.view_data
    try:
        require_tenant_capability(identity, capability)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    return identity


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _checked(values: dict[str, list[str]], name: str) -> bool:
    return _one(values, name) == "on"


def _progress(checklist: CustomerOnboardingChecklist) -> str:
    completed = sum(
        (
            checklist.contact_confirmed,
            checklist.scope_confirmed,
            checklist.commercial_terms_confirmed,
            checklist.access_requirements_confirmed,
            checklist.kickoff_completed,
        )
    )
    return f"{completed}/5"


@router.get("", response_class=HTMLResponse)
def customers(request: Request) -> str:
    identity = _identity(request)
    entries = TenantCustomerStore(_root(request)).list(identity)
    cards = "".join(
        "<article class='card'><p class='muted'>{status} · onboarding {progress}</p><h2>{name}</h2><p><strong>Website:</strong> {website}<br><strong>Offer:</strong> {offer}<br><strong>Projects:</strong> {projects}</p><a class='button' href='/agency/customers/{customer_id}'>Open customer</a></article>".format(
            status=html.escape(customer.status.value.title()),
            progress=html.escape(_progress(customer.onboarding)),
            name=html.escape(customer.business_name),
            website=html.escape(str(customer.website) if customer.website is not None else "No website yet"),
            offer=html.escape(customer.offer_service or "Not recorded"),
            projects=len(customer.project_ids),
            customer_id=html.escape(customer_id, quote=True),
        )
        for customer_id, customer in entries
    ) or "<p class='notice'>No customers yet. A won inbound lead or an outbound prospect marked Customer will create the first onboarding record.</p>"
    body = f"{agency_navigation(identity, current='customers')}<section><h1>Customers</h1><p class='muted'>Won business relationships, onboarding state and linked delivery projects.</p></section><section><div class='cards'>{cards}</div></section>"
    return _page("Customers", body)


@router.get("/{customer_id}", response_class=HTMLResponse)
def customer_detail(customer_id: str, request: Request) -> str:
    identity = _identity(request)
    store = TenantCustomerStore(_root(request))
    try:
        customer = store.load(identity, store.ref(identity, customer_id))
    except TenantCustomerStoreError as exc:
        raise HTTPException(status_code=404, detail="Customer not found.") from exc
    source_href = (
        f"/agency/leads/{customer.source_id}"
        if customer.source_type.value == "lead"
        else f"/agency/prospects/{customer.source_id}"
        if customer.source_type.value == "prospect"
        else ""
    )
    source_link = f"<a class='button secondary' href='{html.escape(source_href, quote=True)}'>Open source {html.escape(customer.source_type.value)}</a>" if source_href else ""
    project_links = "".join(
        f"<a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}'>Open project {html.escape(project_id[:8])}</a>"
        for project_id in customer.project_ids
    ) or "<span class='muted'>No delivery project yet. This is valid for a no-website customer during onboarding.</span>"
    status_options = "".join(
        f"<option value='{item.value}'{' selected' if item is customer.status else ''}>{item.value.title()}</option>"
        for item in CustomerStatus
    )
    checks = "".join(
        f"<label class='check'><input type='checkbox' name='{name}'{' checked' if value else ''}>{html.escape(label)}</label>"
        for name, label, value in (
            ("contact_confirmed", "Primary contact confirmed", customer.onboarding.contact_confirmed),
            ("scope_confirmed", "Service scope confirmed", customer.onboarding.scope_confirmed),
            ("commercial_terms_confirmed", "Commercial terms confirmed", customer.onboarding.commercial_terms_confirmed),
            ("access_requirements_confirmed", "Access/domain/hosting requirements confirmed", customer.onboarding.access_requirements_confirmed),
            ("kickoff_completed", "Kickoff completed", customer.onboarding.kickoff_completed),
        )
    )
    body = f"""{agency_navigation(identity, current='customers')}<section><p><a href='/agency/customers'>← Customers</a></p><h1>{html.escape(customer.business_name)}</h1><p><strong>Status:</strong> {html.escape(customer.status.value.title())}<br><strong>Contact:</strong> {html.escape(customer.contact_name or 'Not recorded')} · {html.escape(customer.contact_email or 'No email')} · {html.escape(customer.phone or 'No phone')}<br><strong>Website:</strong> {html.escape(str(customer.website) if customer.website is not None else 'No website yet')}<br><strong>Offer:</strong> {html.escape(customer.offer_service or 'Not recorded')}<br><strong>Quoted:</strong> {html.escape(f'{customer.currency} {customer.quoted_value}' if customer.quoted_value is not None else 'Not recorded')}<br><strong>Onboarding:</strong> {html.escape(_progress(customer.onboarding))}</p><div class='actions'>{source_link}{project_links}</div></section><section><h2>Customer onboarding</h2><p class='muted'>A customer cannot become Active until all five required onboarding checks are complete.</p><form method='post' action='/agency/customers/{html.escape(customer_id, quote=True)}'><div class='row'><div><label for='status'>Customer status</label><select id='status' name='status'>{status_options}</select></div><div><label for='commercial_notes'>Commercial / onboarding notes</label><textarea id='commercial_notes' name='commercial_notes' maxlength='5000'>{html.escape(customer.commercial_notes)}</textarea></div></div>{checks}<p><button type='submit'>Save customer</button></p></form></section>"""
    return _page(customer.business_name, body)


@router.post("/{customer_id}")
async def save_customer(customer_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request, manage=True)
    store = TenantCustomerStore(_root(request))
    try:
        customer = store.load(identity, store.ref(identity, customer_id))
    except TenantCustomerStoreError as exc:
        raise HTTPException(status_code=404, detail="Customer not found.") from exc
    values = _values(await request.body())
    try:
        next_status = CustomerStatus(_one(values, "status"))
        checklist = CustomerOnboardingChecklist(
            contact_confirmed=_checked(values, "contact_confirmed"),
            scope_confirmed=_checked(values, "scope_confirmed"),
            commercial_terms_confirmed=_checked(values, "commercial_terms_confirmed"),
            access_requirements_confirmed=_checked(values, "access_requirements_confirmed"),
            kickoff_completed=_checked(values, "kickoff_completed"),
        )
        activated_at = customer.activated_at
        if next_status is CustomerStatus.active and activated_at is None:
            activated_at = datetime.now(UTC)
        updated = CustomerRecord.model_validate(
            {
                **customer.model_dump(mode="json"),
                "status": next_status.value,
                "onboarding": checklist.model_dump(mode="json"),
                "commercial_notes": _one(values, "commercial_notes"),
                "updated_at": datetime.now(UTC),
                "activated_at": activated_at,
            }
        )
        store.replace(identity, store.ref(identity, customer_id), updated)
    except (ValueError, ValidationError, TenantCustomerStoreError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Customer update is invalid. Complete onboarding before activation.",
        ) from exc
    return RedirectResponse(f"/agency/customers/{customer_id}", status_code=303)
