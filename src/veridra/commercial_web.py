# ruff: noqa: E501
from __future__ import annotations

import csv
import html
import io
from datetime import UTC, datetime
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import HttpUrl, TypeAdapter, ValidationError

from .commercial_ops import (
    CommercialOpsError,
    EngagementKind,
    EngagementLink,
    EngagementStore,
    RetentionPolicy,
    apply_retention,
    commercial_summary,
    retention_preview,
)
from .lead_store import AuditLead, LeadFormStore, LeadStatus, LeadStore, LeadStoreError

router = APIRouter(tags=["commercial-operations"])

_STYLE = """
body{font:14px Arial;margin:0;background:#f7f8fa;color:#17191c}main{max-width:1200px;margin:36px auto;padding:0 20px}
section{background:#fff;border:1px solid #dfe3e8;border-radius:8px;padding:22px;margin-bottom:18px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.metric{border:1px solid #dfe3e8;padding:15px}.metric strong{display:block;font-size:25px;margin-top:6px}table{width:100%;border-collapse:collapse}th,td{padding:10px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}
label{display:block;font-weight:700;margin:10px 0 4px}input,select,textarea{width:100%;padding:9px;border:1px solid #cfd4da}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.actions{display:flex;gap:8px;flex-wrap:wrap}
button,.button{display:inline-block;background:#22272d;color:#fff;border:0;padding:9px 12px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.danger{background:#b42318}.muted{color:#68707a}@media(max-width:760px){.grid,.row{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main><p><a href='/commercial'>Commercial operations</a> · <a href='/leads'>Leads</a> · <a href='/lead-forms'>Lead forms</a> · <a href='/'>Assessment console</a></p>{body}</main></body></html>"


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _leads() -> LeadStore:
    return LeadStore()


def _engagements() -> EngagementStore:
    return EngagementStore()


def _load_lead(lead_id: str) -> AuditLead:
    try:
        return _leads().load_lead(lead_id)
    except LeadStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _lead_rows(now: datetime) -> str:
    rows: list[str] = []
    for identifier, lead in _leads().list_leads():
        events = [event for _, event in _engagements().list_events(lead_id=identifier)]
        opens = sum(event.kind == EngagementKind.report_open for event in events)
        clicks = sum(event.kind == EngagementKind.cta_click for event in events)
        due = lead.next_follow_up_at is not None and lead.next_follow_up_at.astimezone(UTC) <= now
        rows.append(
            "<tr><td><strong>{name}</strong><br>{email}<br>{company}</td><td>{status}</td><td>{owner}</td><td>{follow}</td><td>{opens}</td><td>{clicks}</td><td><a class='button secondary' href='/commercial/leads/{identifier}'>Manage</a></td></tr>".format(
                name=html.escape(lead.name),
                email=html.escape(str(lead.email)),
                company=html.escape(lead.company or "No company"),
                status=html.escape(lead.status.value),
                owner=html.escape(lead.assigned_owner or "Unassigned"),
                follow=("<strong>Due</strong><br>" if due else "") + html.escape(lead.next_follow_up_at.isoformat() if lead.next_follow_up_at else "Not set"),
                opens=opens,
                clicks=clicks,
                identifier=identifier,
            )
        )
    return "".join(rows) or "<tr><td colspan='7'>No captured leads are available.</td></tr>"


@router.get("/commercial", response_class=HTMLResponse)
def commercial_dashboard() -> str:
    now = datetime.now(UTC)
    summary = commercial_summary(now=now)
    metrics = "".join(
        f"<article class='metric'><span>{html.escape(label)}</span><strong>{value}</strong></article>"
        for label, value in (
            ("Leads", summary.leads_total),
            ("Follow-ups due", summary.follow_ups_due),
            ("Report opens", summary.report_opens),
            ("CTA clicks", summary.cta_clicks),
            ("Webhook delivered", summary.webhook_delivered),
            ("Webhook failed", summary.webhook_failed),
            ("Email delivered", summary.email_delivered),
            ("Email failed", summary.email_failed),
        )
    )
    status = ", ".join(f"{key}: {value}" for key, value in summary.status_counts.items()) or "No leads"
    owners = ", ".join(f"{key}: {value}" for key, value in summary.owner_counts.items()) or "No owners"
    body = (
        "<section><h1>Commercial operations</h1><p class='muted'>Local evidence only. Counts do not claim revenue attribution, marketing ROI or unique-person analytics.</p>"
        f"<div class='grid'>{metrics}</div><p><strong>Status:</strong> {html.escape(status)}<br><strong>Owners:</strong> {html.escape(owners)}</p>"
        "<div class='actions'><a class='button' href='/commercial/engagement.csv'>Export engagement CSV</a><a class='button secondary' href='/commercial/retention'>Retention</a></div></section>"
        "<section><h2>Lead operations</h2><table><thead><tr><th>Lead</th><th>Status</th><th>Owner</th><th>Follow-up</th><th>Opens</th><th>Clicks</th><th>Action</th></tr></thead><tbody>"
        + _lead_rows(now)
        + "</tbody></table></section>"
    )
    return _page("Commercial operations", body)


@router.get("/commercial/leads/{lead_id}", response_class=HTMLResponse)
def manage_lead(lead_id: str) -> str:
    lead = _load_lead(lead_id)
    form = LeadFormStore().load_form(lead.form_id)
    report_link = EngagementLink(
        lead_id=lead_id,
        assessment_id=lead.assessment_id,
        kind=EngagementKind.report_open,
    )
    report_token = _engagements().create_link(report_link)
    cta_url = form.cta_url
    cta_html = "<p class='muted'>CTA tracking is disabled because this lead form has no CTA URL.</p>"
    if cta_url:
        cta_link = EngagementLink(
            lead_id=lead_id,
            assessment_id=lead.assessment_id,
            kind=EngagementKind.cta_click,
            destination=TypeAdapter(HttpUrl).validate_python(cta_url),
        )
        cta_token = _engagements().create_link(cta_link)
        cta_html = f"<p><strong>Tracked CTA URL:</strong> <code>/engage/{cta_token}</code></p>"
    options = "".join(
        f"<option value='{status.value}'{' selected' if status == lead.status else ''}>{status.value.replace('_', ' ').title()}</option>"
        for status in LeadStatus
    )
    events = "".join(
        f"<tr><td>{html.escape(event.kind.value)}</td><td>{html.escape(event.occurred_at.isoformat())}</td><td>{html.escape(event.referrer or '—')}</td></tr>"
        for _, event in _engagements().list_events(lead_id=lead_id)
    ) or "<tr><td colspan='3'>No engagement has been recorded.</td></tr>"
    body = f"""<section><h1>{html.escape(lead.name)}</h1><p><strong>Website:</strong> {html.escape(str(lead.website))}<br><strong>Assessment:</strong> {html.escape(lead.assessment_id)}</p><p><strong>Tracked report URL:</strong> <code>/engage/{report_token}</code></p>{cta_html}</section><section><h2>Ownership and follow-up</h2><form method='post' action='/commercial/leads/{lead_id}'><div class='row'><div><label>Status</label><select name='status'>{options}</select><label>Assigned owner</label><input name='assigned_owner' maxlength='120' value='{html.escape(lead.assigned_owner, quote=True)}'><label>Last contacted</label><input name='last_contacted_at' type='datetime-local' value='{lead.last_contacted_at.strftime('%Y-%m-%dT%H:%M') if lead.last_contacted_at else ''}'></div><div><label>Next follow-up</label><input name='next_follow_up_at' type='datetime-local' value='{lead.next_follow_up_at.strftime('%Y-%m-%dT%H:%M') if lead.next_follow_up_at else ''}'><label>Next action</label><textarea name='next_action' maxlength='500'>{html.escape(lead.next_action)}</textarea><label>Notes</label><textarea name='notes' maxlength='5000'>{html.escape(lead.notes)}</textarea></div></div><p><button>Save commercial record</button></p></form></section><section><h2>Engagement history</h2><table><thead><tr><th>Event</th><th>Time</th><th>Referrer</th></tr></thead><tbody>{events}</tbody></table></section>"""
    return _page("Manage lead", body)


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@router.post("/commercial/leads/{lead_id}")
async def save_commercial_lead(lead_id: str, request: Request) -> RedirectResponse:
    lead = _load_lead(lead_id)
    body = await request.body()
    try:
        updated = AuditLead.model_validate(
            lead.model_copy(
                update={
                    "status": LeadStatus(_single(body, "status")),
                    "assigned_owner": _single(body, "assigned_owner"),
                    "next_action": _single(body, "next_action"),
                    "notes": _single(body, "notes"),
                    "last_contacted_at": _parse_datetime(_single(body, "last_contacted_at")),
                    "next_follow_up_at": _parse_datetime(_single(body, "next_follow_up_at")),
                }
            )
        )
        new_id = _leads().replace(lead_id, updated)
    except (ValidationError, ValueError, LeadStoreError) as exc:
        raise HTTPException(status_code=400, detail="Invalid commercial lead update.") from exc
    return RedirectResponse(f"/commercial/leads/{new_id}", status_code=303)


@router.get("/engage/{token}")
def engagement_redirect(token: str, request: Request) -> RedirectResponse:
    try:
        link = _engagements().load_link(token)
    except CommercialOpsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _load_lead(link.lead_id)
    _engagements().record(
        link,
        user_agent=request.headers.get("user-agent", ""),
        referrer=request.headers.get("referer", ""),
    )
    if link.kind == EngagementKind.report_open:
        return RedirectResponse(f"/history/{link.assessment_id}", status_code=302)
    if link.destination is None:
        raise HTTPException(status_code=400, detail="CTA destination is unavailable.")
    return RedirectResponse(str(link.destination), status_code=302)


@router.get("/commercial/engagement.csv")
def engagement_csv() -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["event_id", "lead_id", "assessment_id", "kind", "occurred_at", "referrer"])
    for identifier, event in _engagements().list_events():
        writer.writerow([identifier, event.lead_id, event.assessment_id, event.kind.value, event.occurred_at.isoformat(), event.referrer])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=veridra-engagement.csv"})


@router.get("/commercial/retention", response_class=HTMLResponse)
def retention_page(lead_days: int = 730, engagement_days: int = 365) -> str:
    try:
        policy = RetentionPolicy(lead_days=lead_days, engagement_days=engagement_days)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid retention policy.") from exc
    preview = retention_preview(policy)
    body = f"""<section><h1>Retention operations</h1><p class='muted'>Only lost or deletion-pending leads older than the threshold are eligible. Assessments, projects and tasks are never pruned here.</p><form method='get' action='/commercial/retention'><div class='row'><div><label>Lead retention days</label><input name='lead_days' type='number' min='30' max='3650' value='{policy.lead_days}'></div><div><label>Engagement retention days</label><input name='engagement_days' type='number' min='30' max='3650' value='{policy.engagement_days}'></div></div><p><button>Preview</button></p></form><p><strong>Eligible leads:</strong> {len(preview.leads)}<br><strong>Eligible engagement events:</strong> {len(preview.engagement_events)}</p><form method='post' action='/commercial/retention/prune'><input type='hidden' name='lead_days' value='{policy.lead_days}'><input type='hidden' name='engagement_days' value='{policy.engagement_days}'><button class='danger'>Apply explicit prune</button></form></section>"""
    return _page("Retention operations", body)


@router.post("/commercial/retention/prune")
async def prune_retention(request: Request) -> RedirectResponse:
    body = await request.body()
    try:
        policy = RetentionPolicy(
            lead_days=int(_single(body, "lead_days")),
            engagement_days=int(_single(body, "engagement_days")),
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid retention policy.") from exc
    apply_retention(retention_preview(policy))
    return RedirectResponse(
        f"/commercial/retention?lead_days={policy.lead_days}&engagement_days={policy.engagement_days}",
        status_code=303,
    )
