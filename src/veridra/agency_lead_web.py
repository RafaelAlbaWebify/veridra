# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .lead_project_conversion_api import LeadProjectConversion, convert_lead_to_project
from .lead_project_link_store import LeadProjectLinkError, LeadProjectLinkStore
from .request_security import require_request_identity
from .tenant_lead_store import TenantLeadStore, TenantLeadStoreError

router = APIRouter(prefix="/agency", tags=["agency-leads"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1050px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}label{display:block;font-weight:700;margin:12px 0 5px}input{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:700px){.row{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _links(request: Request, identity: RequestIdentity) -> LeadProjectLinkStore:
    root = _root(request)
    base = root if root is not None else Path.home() / ".veridra" / "tenants"
    return LeadProjectLinkStore(base / identity.tenant_id / "lead-project-links")


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _require_conversion_capabilities(identity: RequestIdentity) -> None:
    try:
        require_tenant_capability(identity, TenantCapability.manage_leads)
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc


@router.get("/leads", response_class=HTMLResponse)
def agency_leads(request: Request) -> str:
    identity = require_request_identity(request)
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
        action = (
            f"<a class='button secondary' href='/agency/projects/{html.escape(link.project_id, quote=True)}'>Open project</a>"
            if link is not None
            else f"<a class='button' href='/agency/leads/{html.escape(lead_id, quote=True)}/convert'>Convert to client project</a>"
        )
        rows.append(
            f"<tr><td>{html.escape(lead.name)}<br><span class='muted'>{html.escape(lead.company or 'No company')}</span></td><td>{html.escape(str(lead.website))}</td><td>{html.escape(str(lead.email))}</td><td>{html.escape(lead.status.value)}</td><td>{action}</td></tr>"
        )
    table = (
        "<table><thead><tr><th>Prospect</th><th>Website</th><th>Email</th><th>Status</th><th>Next action</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else "<p class='notice'>No tenant audit leads are available yet.</p>"
    )
    body = f"<section><p><a href='/agency'>Agency workflow</a></p><h1>Audit leads</h1><p class='muted'>Convert a qualified captured audit into persistent client work without re-entering its website or assessment.</p>{table}</section>"
    return _page("Audit leads", body)


@router.get("/leads/{lead_id}/convert", response_class=HTMLResponse)
def lead_conversion_confirmation(lead_id: str, request: Request) -> str:
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
    body = f"""<section><p><a href='/agency/leads'>Audit leads</a></p><h1>Convert lead to client project</h1><p class='notice'><strong>Prospect:</strong> {html.escape(lead.name)}<br><strong>Website:</strong> {html.escape(str(lead.website))}<br><strong>Assessment:</strong> {html.escape(lead.assessment_id)}</p><p>The website, assessment and tenant report profile are resolved server-side from this tenant-owned lead. Opening this page creates nothing.</p><form method='post' action='/agency/leads/{html.escape(lead_id, quote=True)}/convert'><div class='row'><div><label for='project_name'>Project name</label><input id='project_name' name='project_name' maxlength='120' value='{html.escape(project_name, quote=True)}' required></div><div><label for='client_label'>Client label</label><input id='client_label' name='client_label' maxlength='120' value='{html.escape(client_label, quote=True)}'></div></div><p><button type='submit'>Create client project</button> <a class='button secondary' href='/agency/leads'>Cancel</a></p></form></section>"""
    return _page("Convert lead", body)


@router.post("/leads/{lead_id}/convert")
async def submit_lead_conversion(lead_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_conversion_capabilities(identity)
    body = await request.body()
    try:
        payload = LeadProjectConversion(
            project_name=_single(body, "project_name"),
            client_label=_single(body, "client_label") or None,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Lead conversion input is invalid.") from exc
    created = convert_lead_to_project(lead_id, payload, request, identity)
    return RedirectResponse(f"/agency/projects/{created.project_id}", status_code=303)
