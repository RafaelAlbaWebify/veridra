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
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .lead_activity import LeadActivityError, TenantLeadActivityStore
from .lead_project_conversion_api import LeadProjectConversion, convert_lead_to_project
from .lead_project_link_store import LeadProjectLinkError, LeadProjectLinkStore
from .lead_store import AuditLead, LeadStatus
from .request_security import require_request_identity
from .tenant_lead_store import TenantLeadStore, TenantLeadStoreError

router = APIRouter(prefix="/agency", tags=["agency-leads"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1050px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.danger{background:#a23333}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.actions{display:flex;gap:8px;flex-wrap:wrap}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:110px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.timeline{list-style:none;padding:0;margin:0}.timeline li{padding:12px 0;border-bottom:1px solid #e5e7eb}.timeline time{display:block;color:#68707a;font-size:12px;margin-bottom:4px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}@media(max-width:700px){.row{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _activity_root(request: Request) -> Path:
    return _root(request) or Path.home() / ".veridra" / "tenants"


def _links(request: Request, identity: RequestIdentity) -> LeadProjectLinkStore:
    return LeadProjectLinkStore(_activity_root(request) / identity.tenant_id / "lead-project-links")


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _require_manage_leads(identity: RequestIdentity) -> None:
    try:
        require_tenant_capability(identity, TenantCapability.manage_leads)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc


def _require_conversion_capabilities(identity: RequestIdentity) -> None:
    try:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc


def _load_lead(request: Request, identity: RequestIdentity, lead_id: str) -> AuditLead:
    leads = TenantLeadStore(_root(request))
    try:
        return leads.load(identity, leads.ref(identity, lead_id))
    except TenantLeadStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead not found.") from exc


def _datetime_local(value: object) -> str:
    if value is None:
        return ""
    isoformat = getattr(value, "isoformat", None)
    if not callable(isoformat):
        return ""
    return str(isoformat(timespec="minutes")).replace("+00:00", "")


def _money(value: object) -> str:
    return "" if value is None else str(value)


@router.get("/leads", response_class=HTMLResponse)
def agency_leads(request: Request) -> str:
    identity = require_request_identity(request)
    _require_manage_leads(identity)
    leads = TenantLeadStore(_root(request))
    try:
        entries = leads.list(identity)
    except TenantLeadStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead data not found.") from exc
    link_store = _links(request, identity)
    rows: list[str] = []
    for lead_id, lead in entries:
        try:
            link = link_store.load(lead_id)
        except LeadProjectLinkError as exc:
            raise HTTPException(status_code=404, detail="Lead data not found.") from exc
        primary = f"<a class='button secondary' href='/agency/projects/{html.escape(link.project_id, quote=True)}'>Open project</a>" if link is not None else f"<a class='button' href='/agency/leads/{html.escape(lead_id, quote=True)}/convert'>Convert to client project</a>"
        rows.append(f"<tr><td>{html.escape(lead.name)}<br><span class='muted'>{html.escape(lead.company or 'No company')}</span></td><td>{html.escape(lead.status.value)}</td><td>{html.escape(lead.offer_service or '—')}</td><td>{html.escape(f'{lead.currency} {lead.quoted_value}' if lead.quoted_value is not None else '—')}</td><td>{html.escape(lead.next_action or '—')}</td><td><div class='actions'><a class='button secondary' href='/agency/leads/{html.escape(lead_id, quote=True)}'>Open lead</a>{primary}</div></td></tr>")
    table = "<table><thead><tr><th>Prospect</th><th>Status</th><th>Offer</th><th>Quoted</th><th>Next action</th><th>Actions</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>" if rows else "<p class='notice'>No tenant audit leads are available yet.</p>"
    navigation = agency_navigation(identity, current="leads")
    return _page("Audit leads", f"{navigation}<section><p><a href='/agency'>Agency home</a></p><h1>Audit leads</h1><p class='muted'>Qualify prospects, record commercial value and follow-up work, then convert won leads into client projects.</p>{table}</section>")


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def agency_lead_detail(lead_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    _require_manage_leads(identity)
    lead = _load_lead(request, identity, lead_id)
    try:
        link = _links(request, identity).load(lead_id)
        events = TenantLeadActivityStore(_activity_root(request)).list(identity, lead_id)
    except (LeadProjectLinkError, LeadActivityError) as exc:
        raise HTTPException(status_code=404, detail="Lead data not found.") from exc
    status_options = "".join(f"<option value='{item.value}'{' selected' if item == lead.status else ''}>{html.escape(item.value.replace('_', ' ').title())}</option>" for item in LeadStatus)
    project_action = f"<a class='button secondary' href='/agency/projects/{html.escape(link.project_id, quote=True)}'>Open client project</a>" if link is not None else f"<a class='button' href='/agency/leads/{html.escape(lead_id, quote=True)}/convert'>Convert to client project</a>"
    timeline = "".join(f"<li><time>{html.escape(event.occurred_at.isoformat())}</time><strong>{html.escape(event.event_type.value.replace('_', ' ').title())}</strong><div>{html.escape(event.summary)}</div></li>" for event in reversed(events)) or "<li class='muted'>No activity recorded yet.</li>"
    navigation = agency_navigation(identity, current="leads")
    body = f"""{navigation}<section><p><a href='/agency'>Agency home</a> · <a href='/agency/leads'>Audit leads</a></p><h1>{html.escape(lead.name)}</h1><p><strong>Company:</strong> {html.escape(lead.company or 'Not supplied')}<br><strong>Email:</strong> {html.escape(str(lead.email))}<br><strong>Phone:</strong> {html.escape(lead.phone or 'Not supplied')}<br><strong>Website:</strong> {html.escape(str(lead.website))}</p><div class='actions'>{project_action}</div></section><section><h2>Commercial qualification</h2><form method='post' action='/agency/leads/{html.escape(lead_id, quote=True)}'><div class='row'><div><label for='status'>Status</label><select id='status' name='status'>{status_options}</select></div><div><label for='assigned_owner'>Owner</label><input id='assigned_owner' name='assigned_owner' maxlength='120' value='{html.escape(lead.assigned_owner, quote=True)}'></div><div><label for='offer_service'>Offer / service</label><input id='offer_service' name='offer_service' maxlength='160' value='{html.escape(lead.offer_service, quote=True)}'></div><div><label for='currency'>Currency</label><input id='currency' name='currency' minlength='3' maxlength='3' value='{html.escape(lead.currency, quote=True)}'></div><div><label for='quoted_value'>Quoted value</label><input id='quoted_value' name='quoted_value' type='number' min='0' step='0.01' value='{html.escape(_money(lead.quoted_value), quote=True)}'></div><div><label for='expected_value'>Expected value</label><input id='expected_value' name='expected_value' type='number' min='0' step='0.01' value='{html.escape(_money(lead.expected_value), quote=True)}'></div><div><label for='last_contacted_at'>Last contacted</label><input id='last_contacted_at' name='last_contacted_at' type='datetime-local' value='{html.escape(_datetime_local(lead.last_contacted_at), quote=True)}'></div><div><label for='next_follow_up_at'>Next follow-up</label><input id='next_follow_up_at' name='next_follow_up_at' type='datetime-local' value='{html.escape(_datetime_local(lead.next_follow_up_at), quote=True)}'></div></div><label for='next_action'>Next action</label><input id='next_action' name='next_action' maxlength='500' value='{html.escape(lead.next_action, quote=True)}'><label for='loss_reason'>Loss reason</label><input id='loss_reason' name='loss_reason' maxlength='500' value='{html.escape(lead.loss_reason, quote=True)}'><label for='notes'>Notes</label><textarea id='notes' name='notes' maxlength='5000'>{html.escape(lead.notes)}</textarea><p><button type='submit'>Save lead</button></p></form></section><section><h2>Activity history</h2><p class='muted'>Append-only record of meaningful CRM changes.</p><ul class='timeline'>{timeline}</ul></section>"""
    return _page("Lead detail", body)


@router.post("/leads/{lead_id}")
async def save_agency_lead(lead_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_manage_leads(identity)
    lead = _load_lead(request, identity, lead_id)
    body = await request.body()
    new_status = LeadStatus(_single(body, "status"))
    now = datetime.now(UTC)
    loss_reason = _single(body, "loss_reason")
    if new_status is LeadStatus.lost and not loss_reason:
        raise HTTPException(status_code=400, detail="A loss reason is required when a lead is lost.")
    data = lead.model_dump(mode="python")
    data.update({
        "status": new_status,
        "notes": _single(body, "notes"),
        "assigned_owner": _single(body, "assigned_owner"),
        "next_action": _single(body, "next_action"),
        "last_contacted_at": _single(body, "last_contacted_at") or None,
        "next_follow_up_at": _single(body, "next_follow_up_at") or None,
        "offer_service": _single(body, "offer_service"),
        "quoted_value": _single(body, "quoted_value") or None,
        "expected_value": _single(body, "expected_value") or None,
        "currency": (_single(body, "currency") or "EUR").upper(),
        "loss_reason": loss_reason,
        "won_at": now if new_status is LeadStatus.won and lead.status is not LeadStatus.won else lead.won_at,
        "lost_at": now if new_status is LeadStatus.lost and lead.status is not LeadStatus.lost else lead.lost_at,
    })
    try:
        updated = AuditLead.model_validate(data)
        TenantLeadStore(_root(request)).replace(identity, TenantLeadStore.ref(identity, lead_id), updated)
    except (ValidationError, ValueError, TenantLeadStoreError) as exc:
        raise HTTPException(status_code=400, detail="Lead update is invalid.") from exc
    return RedirectResponse(f"/agency/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/delete")
def delete_agency_lead(lead_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_manage_leads(identity)
    leads = TenantLeadStore(_root(request))
    try:
        leads.delete(identity, leads.ref(identity, lead_id))
    except TenantLeadStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead not found.") from exc
    return RedirectResponse("/agency/leads", status_code=303)


@router.get("/leads/{lead_id}/convert", response_class=HTMLResponse, response_model=None)
def lead_conversion_confirmation(lead_id: str, request: Request) -> str | RedirectResponse:
    identity = require_request_identity(request)
    _require_conversion_capabilities(identity)
    leads = TenantLeadStore(_root(request))
    try:
        lead = leads.load(identity, leads.ref(identity, lead_id))
        link = _links(request, identity).load(lead_id)
    except (TenantLeadStoreError, LeadProjectLinkError) as exc:
        raise HTTPException(status_code=404, detail="Lead conversion source not found.") from exc
    if link is not None:
        return RedirectResponse(f"/agency/projects/{link.project_id}", status_code=303)
    project_name = lead.company or f"{lead.name} website"
    client_label = lead.company or lead.name
    navigation = agency_navigation(identity, current="leads")
    body = f"""{navigation}<section><p><a href='/agency'>Agency home</a> · <a href='/agency/leads'>Audit leads</a> · <a href='/agency/leads/{html.escape(lead_id, quote=True)}'>Lead detail</a></p><h1>Convert lead to client project</h1><p class='notice'><strong>Prospect:</strong> {html.escape(lead.name)}<br><strong>Website:</strong> {html.escape(str(lead.website))}<br><strong>Offer:</strong> {html.escape(lead.offer_service or 'Not recorded')}<br><strong>Quoted:</strong> {html.escape(f'{lead.currency} {lead.quoted_value}' if lead.quoted_value is not None else 'Not recorded')}</p><form method='post' action='/agency/leads/{html.escape(lead_id, quote=True)}/convert'><div class='row'><div><label for='project_name'>Project name</label><input id='project_name' name='project_name' maxlength='120' value='{html.escape(project_name, quote=True)}' required></div><div><label for='client_label'>Client label</label><input id='client_label' name='client_label' maxlength='120' value='{html.escape(client_label, quote=True)}'></div></div><p><button type='submit'>Create client project</button> <a class='button secondary' href='/agency/leads/{html.escape(lead_id, quote=True)}'>Cancel</a></p></form></section>"""
    return _page("Convert lead", body)


@router.post("/leads/{lead_id}/convert")
async def submit_lead_conversion(lead_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_conversion_capabilities(identity)
    body = await request.body()
    try:
        payload = LeadProjectConversion(project_name=_single(body, "project_name"), client_label=_single(body, "client_label") or None)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Lead conversion input is invalid.") from exc
    created = convert_lead_to_project(lead_id, payload, request, identity)
    return RedirectResponse(f"/agency/projects/{created.project_id}", status_code=303)
