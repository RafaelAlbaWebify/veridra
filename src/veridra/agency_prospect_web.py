# ruff: noqa: E501
from __future__ import annotations

import html
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode

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
from .prospect import (
    Prospect,
    ProspectCommercialLossReason,
    ProspectDecision,
    ProspectRejectionReason,
    ProspectStatus,
    StageAQualification,
    prospect_identifier,
)
from .prospect_activity import ProspectActivityError, TenantProspectActivityStore
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError

router = APIRouter(prefix="/agency/prospects", tags=["agency-prospects"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1180px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.warning{border-left-color:#b7791f;background:#fff8e6}.actions{display:flex;gap:8px;flex-wrap:wrap}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:100px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.score-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.timeline{list-style:none;padding:0;margin:0}.timeline li{padding:12px 0;border-bottom:1px solid #e5e7eb}.timeline time{display:block;color:#68707a;font-size:12px;margin-bottom:4px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}.disclosure summary{cursor:pointer;font-size:18px;font-weight:700;list-style-position:outside}.disclosure[open] summary{margin-bottom:14px}.summary-note{font-size:13px;font-weight:400;color:#68707a;margin-left:8px}@media(max-width:760px){.row,.score-grid{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""

_COMMERCIAL_STATUSES = (
    ProspectStatus.approved_for_outreach,
    ProspectStatus.contacted,
    ProspectStatus.responded,
    ProspectStatus.conversation,
    ProspectStatus.proposal,
    ProspectStatus.customer,
    ProspectStatus.lost,
)
_TERMINAL_QUALIFICATION_STATUSES = {
    ProspectStatus.unsuitable,
    ProspectStatus.duplicate,
    ProspectStatus.archived,
}


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _activity_root(request: Request) -> Path:
    return _root(request) or Path.home() / ".veridra" / "tenants"


def _store(request: Request) -> TenantProspectStore:
    return TenantProspectStore(_root(request))


def _identity(request: Request) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_leads)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    return identity


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Prospect workbench is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Prospect request is not permitted.") from exc


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _datetime_local(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat(timespec="minutes").replace("+00:00", "")


def _load(request: Request, identity: RequestIdentity, prospect_id: str) -> Prospect:
    store = _store(request)
    try:
        return store.load(identity, store.ref(identity, prospect_id))
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc


def _audit_url(prospect: Prospect) -> str:
    if prospect.website is None:
        return ""
    return f"/agency/quick-audit?{urlencode({'target': str(prospect.website)})}"


def _decision(prospect: Prospect) -> str:
    if prospect.qualification is None:
        return "Not scored"
    return f"{prospect.qualification.score}/14 · {prospect.qualification.decision.value.replace('_', ' ')}"


def _commercial_status_options(prospect: Prospect) -> str:
    current = prospect.status
    return "".join(
        f"<option value='{item.value}'{' selected' if current is item else ''}>{item.value.replace('_', ' ').title()}</option>"
        for item in _COMMERCIAL_STATUSES
    )


def _commercial_loss_options(prospect: Prospect) -> str:
    current = prospect.commercial_loss_reason.value if prospect.commercial_loss_reason else ""
    return "<option value=''>None</option>" + "".join(
        f"<option value='{item.value}'{' selected' if current == item.value else ''}>{item.value.replace('_', ' ').title()}</option>"
        for item in ProspectCommercialLossReason
    )


@router.get("", response_class=HTMLResponse)
def prospect_index(request: Request) -> str:
    identity = _identity(request)
    entries = _store(request).list(identity)
    rows: list[str] = []
    for prospect_id, prospect in entries:
        website = str(prospect.website) if prospect.website is not None else "—"
        audit_url = _audit_url(prospect)
        audit_action = (
            f"<a class='button secondary' href='{html.escape(audit_url, quote=True)}'>Start audit</a>"
            if audit_url and prospect.status not in _TERMINAL_QUALIFICATION_STATUSES
            else ""
        )
        follow_up = prospect.next_follow_up_at.isoformat() if prospect.next_follow_up_at else "—"
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(prospect.business_name)}</strong><br><span class='muted'>{html.escape(prospect.sector or 'Unclassified')}</span></td>"
            f"<td>{html.escape(prospect.locality or '—')}<br><span class='muted'>{html.escape(prospect.administrative_area or '')}</span></td>"
            f"<td>{html.escape(website)}</td>"
            f"<td><span class='badge'>{html.escape(prospect.status.value)}</span></td>"
            f"<td>{html.escape(follow_up)}<br><span class='muted'>{html.escape(prospect.next_action or 'No action')}</span></td>"
            f"<td>{html.escape(_decision(prospect))}</td>"
            f"<td><div class='actions'><a class='button' href='/agency/prospects/{html.escape(prospect_id, quote=True)}'>Review</a>{audit_action}</div></td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr><th>Business</th><th>Territory</th><th>Website</th><th>Status</th><th>Follow-up</th><th>Qualification</th><th>Actions</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else "<p class='notice'>No outbound prospects yet. Add one manually or discover/import prospects.</p>"
    )
    navigation = agency_navigation(identity, current="prospects")
    body = f"{navigation}<section><div class='actions'><a class='button' href='/agency/prospects/new'>Add prospect</a><a class='button secondary' href='/agency/prospects/discover'>Discover prospects</a></div><h1>Webify prospects</h1><p class='muted'>Businesses discovered for possible website improvement work. Qualify commercial fit, audit credible opportunities and record the real sales outcome.</p>{table}</section>"
    return _page("Webify prospects", body)


@router.get("/new", response_class=HTMLResponse)
def new_prospect_page(request: Request) -> str:
    identity = _identity(request)
    navigation = agency_navigation(identity, current="prospects")
    body = f"{navigation}<section><p><a href='/agency/prospects'>← Prospects</a></p><h1>Add prospect</h1><p class='muted'>Use this for a business you found manually. Discovery adapters create the same record type.</p><form method='post' action='/agency/prospects/new'><div class='row'><div><label>Business name</label><input name='business_name' maxlength='200' required></div><div><label>Website</label><input name='website' maxlength='2048' placeholder='https://example.com'></div></div><div class='row'><div><label>Sector</label><input name='sector' maxlength='120'></div><div><label>Phone</label><input name='phone' maxlength='80'></div></div><div class='row'><div><label>Locality</label><input name='locality' maxlength='120'></div><div><label>Administrative area</label><input name='administrative_area' maxlength='120'></div></div><div class='row'><div><label>Country code</label><input name='country_code' maxlength='2' placeholder='US, IE, GB, etc.'></div><div><label>Contact email</label><input name='contact_email' type='email' maxlength='254'></div></div><label>Evidence / discovery note</label><textarea name='evidence_summary' maxlength='4000' placeholder='Where the business was found and why it may be worth reviewing.'></textarea><button type='submit'>Create prospect</button></form></section>"
    return _page("Add prospect", body)


@router.post("/new", response_model=None)
async def create_prospect(request: Request) -> HTMLResponse | RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    try:
        prospect = Prospect.model_validate(
            {
                "business_name": _one(values, "business_name"),
                "website": _one(values, "website") or None,
                "sector": _one(values, "sector"),
                "locality": _one(values, "locality"),
                "administrative_area": _one(values, "administrative_area"),
                "country_code": _one(values, "country_code").upper(),
                "phone": _one(values, "phone"),
                "contact_email": _one(values, "contact_email"),
                "provider": "manual",
                "provider_key": "",
                "evidence_summary": _one(values, "evidence_summary"),
                "status": ProspectStatus.needs_review,
            }
        )
    except ValidationError as exc:
        return HTMLResponse(
            _page(
                "Invalid prospect",
                f"<section><h1>Prospect could not be saved</h1><p class='muted'>{html.escape(str(exc))}</p><p><a href='/agency/prospects/new'>Return to form</a></p></section>",
            ),
            status_code=400,
        )
    prospect_id = prospect_identifier(prospect)
    store = _store(request)
    try:
        store.load(identity, store.ref(identity, prospect_id))
    except TenantProspectStoreError:
        store.save(identity, prospect)
    else:
        return HTMLResponse(
            _page(
                "Duplicate prospect",
                "<section><h1>Prospect already exists</h1><p class='muted'>Review the existing record instead of replacing its qualification or outreach state.</p><p><a href='/agency/prospects'>Return to prospects</a></p></section>",
            )
        )
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)


@router.get("/{prospect_id}", response_class=HTMLResponse)
def prospect_detail(prospect_id: str, request: Request) -> str:
    identity = _identity(request)
    prospect = _load(request, identity, prospect_id)
    navigation = agency_navigation(identity, current="prospects")
    website = str(prospect.website) if prospect.website is not None else "—"
    audit_url = _audit_url(prospect)
    audit_action = f"<a class='button' href='{html.escape(audit_url, quote=True)}'>Start website audit</a>" if audit_url else "<span class='muted'>Add a website before auditing.</span>"
    try:
        events = TenantProspectActivityStore(_activity_root(request)).list(identity, prospect_id)
    except ProspectActivityError as exc:
        raise HTTPException(status_code=404, detail="Prospect activity could not be read.") from exc
    timeline = "".join(
        f"<li><time>{html.escape(event.occurred_at.isoformat())}</time><strong>{html.escape(event.event_type.value.replace('_', ' ').title())}</strong><div>{html.escape(event.summary)}</div></li>"
        for event in reversed(events)
    ) or "<li class='muted'>No activity recorded yet.</li>"
    qualification = prospect.qualification
    values = {
        "active_real_business": qualification.active_real_business if qualification else 0,
        "website_commercial_importance": qualification.website_commercial_importance if qualification else 0,
        "business_economic_value": qualification.business_economic_value if qualification else 0,
        "business_size_fit": qualification.business_size_fit if qualification else 0,
        "decision_maker_reachability": qualification.decision_maker_reachability if qualification else 0,
        "website_manageability": qualification.website_manageability if qualification else 0,
        "no_existing_web_team": qualification.no_existing_web_team if qualification else 0,
    }
    score_fields = "".join(
        f"<div><label>{html.escape(label)}</label><select name='{name}'>"
        + "".join(f"<option value='{value}'{' selected' if selected == value else ''}>{value}</option>" for value in (0, 1, 2))
        + "</select></div>"
        for name, label, selected in (
            ("active_real_business", "Active real business", values["active_real_business"]),
            ("website_commercial_importance", "Website commercial importance", values["website_commercial_importance"]),
            ("business_economic_value", "Business economic value", values["business_economic_value"]),
            ("business_size_fit", "Business size / Webify fit", values["business_size_fit"]),
            ("decision_maker_reachability", "Decision-maker reachability", values["decision_maker_reachability"]),
            ("website_manageability", "Website manageability", values["website_manageability"]),
            ("no_existing_web_team", "No obvious agency/internal web team", values["no_existing_web_team"]),
        )
    )
    reason = qualification.reason if qualification else ""
    current_rejection = prospect.rejection_reason.value if prospect.rejection_reason else ""
    rejection_options = "<option value=''>None</option>" + "".join(
        f"<option value='{item.value}'{' selected' if current_rejection == item.value else ''}>{item.value.replace('_', ' ').title()}</option>"
        for item in ProspectRejectionReason
    )
    qualification_open = " open" if qualification is None else ""
    qualification_section = f"<section><details class='disclosure'{qualification_open}><summary>Qualification score <span class='summary-note'>{html.escape(_decision(prospect))}</span></summary><p class='muted'>Score each criterion 0–2. 11–14 is ready for audit, 8–10 is hold/secondary, and 0–7 is reject. A rejected prospect needs an explicit reason before it becomes terminally unsuitable.</p><form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/qualify'><div class='score-grid'>{score_fields}</div><label>Why this score?</label><textarea name='reason' maxlength='1000' required>{html.escape(reason)}</textarea><label>Explicit rejection reason (optional)</label><select name='rejection_reason'>{rejection_options}</select><button type='submit'>Save qualification</button></form></details></section>"
    if prospect.status in _TERMINAL_QUALIFICATION_STATUSES:
        commercial_section = "<section><h2>Commercial funnel</h2><p class='notice warning'>This prospect is terminally rejected/archived at qualification stage. Re-open qualification before recording outreach.</p></section>"
    else:
        commercial_section = f"<section><h2>Commercial funnel</h2><p class='muted'>Record what actually happened after qualification. This is sales evidence, not an automated outreach action.</p><form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/commercial'><div class='row'><div><label for='commercial_status'>Funnel stage</label><select id='commercial_status' name='status'>{_commercial_status_options(prospect)}</select></div><div><label for='commercial_loss_reason'>Loss reason</label><select id='commercial_loss_reason' name='commercial_loss_reason'>{_commercial_loss_options(prospect)}</select></div></div><div class='row'><div><label for='outreach_offer'>Offer used</label><input id='outreach_offer' name='outreach_offer' maxlength='240' value='{html.escape(prospect.outreach_offer, quote=True)}' placeholder='e.g. Website Improvement Sprint'></div><div><label for='message_variant'>Message variant / cohort</label><input id='message_variant' name='message_variant' maxlength='120' value='{html.escape(prospect.message_variant, quote=True)}' placeholder='e.g. dental-dublin-v1'></div><div><label for='last_contacted_at'>Last contacted</label><input id='last_contacted_at' name='last_contacted_at' type='datetime-local' value='{html.escape(_datetime_local(prospect.last_contacted_at), quote=True)}'></div><div><label for='next_follow_up_at'>Next follow-up</label><input id='next_follow_up_at' name='next_follow_up_at' type='datetime-local' value='{html.escape(_datetime_local(prospect.next_follow_up_at), quote=True)}'></div></div><label for='next_action'>Next action</label><input id='next_action' name='next_action' maxlength='500' value='{html.escape(prospect.next_action, quote=True)}' placeholder='e.g. Follow up by phone on Monday'><label for='commercial_note'>Commercial note</label><textarea id='commercial_note' name='commercial_note' maxlength='2000' placeholder='Channel, reply context, objection, proposal note or other useful evidence.'>{html.escape(prospect.commercial_note)}</textarea><p class='notice'>A prospect marked <strong>lost</strong> requires a loss reason. For every other stage the loss reason is cleared automatically.</p><button type='submit'>Save commercial progress</button></form></section>"
    activity_section = f"<section><details class='disclosure'><summary>Activity history <span class='summary-note'>{len(events)} event{'s' if len(events) != 1 else ''}</span></summary><p class='muted'>Append-only record of meaningful outbound CRM changes.</p><ul class='timeline'>{timeline}</ul></details></section>"
    body = f"{navigation}<section><p><a href='/agency/prospects'>← Prospects</a></p><h1>{html.escape(prospect.business_name)}</h1><p><span class='badge'>{html.escape(prospect.status.value)}</span> · Qualification: {html.escape(_decision(prospect))}</p><p><strong>Website:</strong> {html.escape(website)}<br><strong>Sector:</strong> {html.escape(prospect.sector or '—')}<br><strong>Territory:</strong> {html.escape(prospect.locality or '—')}, {html.escape(prospect.administrative_area or '—')}<br><strong>Contact:</strong> {html.escape(prospect.contact_email or prospect.phone or '—')}<br><strong>Next action:</strong> {html.escape(prospect.next_action or '—')}</p><p class='notice'>{html.escape(prospect.evidence_summary or 'No discovery evidence recorded yet.')}</p><div class='actions'>{audit_action}</div></section>{qualification_section}{commercial_section}{activity_section}"
    return _page(prospect.business_name, body)


@router.post("/{prospect_id}/qualify")
async def qualify_prospect(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    prospect = _load(request, identity, prospect_id)
    values = _values(await request.body())
    try:
        rejection_raw = _one(values, "rejection_reason")
        rejection = ProspectRejectionReason(rejection_raw) if rejection_raw else None
        qualification = StageAQualification(
            active_real_business=int(_one(values, "active_real_business")),
            website_commercial_importance=int(_one(values, "website_commercial_importance")),
            business_economic_value=int(_one(values, "business_economic_value")),
            business_size_fit=int(_one(values, "business_size_fit")),
            decision_maker_reachability=int(_one(values, "decision_maker_reachability")),
            website_manageability=int(_one(values, "website_manageability")),
            no_existing_web_team=int(_one(values, "no_existing_web_team")),
            reason=_one(values, "reason"),
            rejection_reason=rejection,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Qualification values are invalid.") from exc

    if qualification.decision is ProspectDecision.send_to_audit:
        next_status = ProspectStatus.ready_for_audit
    elif qualification.decision is ProspectDecision.hold:
        next_status = ProspectStatus.qualified
    elif rejection is not None:
        next_status = ProspectStatus.unsuitable
    else:
        next_status = ProspectStatus.needs_review

    updated = Prospect.model_validate(
        {
            **prospect.model_dump(mode="json"),
            "qualification": qualification.model_dump(mode="json"),
            "status": next_status,
            "human_verified": True,
            "rejection_reason": rejection.value if rejection is not None else None,
            "updated_at": datetime.now(UTC),
        }
    )
    store = _store(request)
    try:
        store.replace(identity, store.ref(identity, prospect_id), updated)
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)


@router.post("/{prospect_id}/commercial")
async def update_commercial_progress(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    prospect = _load(request, identity, prospect_id)
    if prospect.status in _TERMINAL_QUALIFICATION_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Terminally rejected or archived prospects cannot enter the commercial funnel.",
        )
    values = _values(await request.body())
    try:
        next_status = ProspectStatus(_one(values, "status"))
        if next_status not in _COMMERCIAL_STATUSES:
            raise ValueError("Unsupported commercial funnel status.")
        loss_raw = _one(values, "commercial_loss_reason")
        loss_reason = (
            ProspectCommercialLossReason(loss_raw)
            if next_status is ProspectStatus.lost and loss_raw
            else None
        )
        updated = Prospect.model_validate(
            {
                **prospect.model_dump(mode="json"),
                "status": next_status,
                "outreach_offer": _one(values, "outreach_offer"),
                "message_variant": _one(values, "message_variant"),
                "commercial_loss_reason": (
                    loss_reason.value if loss_reason is not None else None
                ),
                "commercial_note": _one(values, "commercial_note"),
                "last_contacted_at": _one(values, "last_contacted_at") or None,
                "next_follow_up_at": _one(values, "next_follow_up_at") or None,
                "next_action": _one(values, "next_action"),
                "human_verified": True,
                "updated_at": datetime.now(UTC),
            }
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Commercial funnel values are invalid. Lost prospects require a loss reason.",
        ) from exc

    store = _store(request)
    try:
        store.replace(identity, store.ref(identity, prospect_id), updated)
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)
