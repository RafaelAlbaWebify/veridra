from __future__ import annotations

import csv
import html
import io
import time
from collections import defaultdict, deque
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .collector import CollectionError
from .core import UnsafeTargetError
from .history import HistoryError, HistoryStore
from .lead_delivery import LeadDeliveryStore, deliver_lead_webhook
from .lead_store import (
    AuditLead,
    LeadFormConfig,
    LeadFormStore,
    LeadStatus,
    LeadStore,
    LeadStoreError,
    consent_timestamp,
)
from .profile_store import ProfileStore, ProfileStoreError
from .service import assess_url

router = APIRouter(tags=["leads"])

_RATE_WINDOW_SECONDS = 3600.0
_RATE_LIMIT = 5
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _forms() -> LeadFormStore:
    return LeadFormStore()


def _leads() -> LeadStore:
    return LeadStore()


def _history() -> HistoryStore:
    return HistoryStore()


def _deliveries() -> LeadDeliveryStore:
    return LeadDeliveryStore()


def _page(title: str, body: str, *, public: bool = False) -> str:
    navigation = (
        ""
        if public
        else "<p><a href='/lead-forms'>Lead forms</a> · <a href='/leads'>Leads</a> · <a href='/'>Assessment console</a></p>"
    )
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:1050px;margin:36px auto;padding:0 20px}}section{{background:#fff;border:1px solid #dfe3e8;border-radius:9px;padding:22px;margin-bottom:18px}}label{{display:block;font-weight:700;margin:12px 0 5px}}input,select,textarea{{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}}textarea{{min-height:110px}}button,.button{{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}}.secondary{{background:#5f6873}}.danger{{background:#b42318}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top;overflow-wrap:anywhere}}.muted{{color:#68707a}}.actions{{display:flex;gap:8px;flex-wrap:wrap}}form.inline{{display:inline}}.check{{display:flex;align-items:flex-start;gap:9px}}.check input{{width:auto;margin-top:3px}}.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.metric{{border:1px solid #dfe3e8;border-radius:8px;padding:15px}}.metric strong{{display:block;font-size:25px;margin-top:7px}}code,pre{{overflow-wrap:anywhere}}@media(max-width:760px){{.row,.metrics{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}</style></head><body><main>{navigation}{body}</main></body></html>"""


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _parse_form_config(body: bytes) -> LeadFormConfig:
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)

    def value(name: str) -> str:
        return parsed.get(name, [""])[0].strip()

    origins = tuple(
        item.strip()
        for raw in value("allowed_origins").replace(",", "\n").splitlines()
        if (item := raw.strip())
    )
    profile_id = value("profile_id") or None
    if profile_id is not None:
        try:
            ProfileStore().load(profile_id)
        except ProfileStoreError as exc:
            raise HTTPException(status_code=400, detail="Selected report profile was not found.") from exc
    try:
        return LeadFormConfig(
            organisation_label=value("organisation_label"),
            heading=value("heading") or "Get your free website report",
            introduction=value("introduction"),
            submit_label=value("submit_label") or "Get my report",
            consent_text=value("consent_text"),
            collect_company=value("collect_company") == "on",
            collect_phone=value("collect_phone") == "on",
            allowed_origins=origins,
            profile_id=profile_id,
            webhook_url=value("webhook_url") or None,
            webhook_secret=value("webhook_secret") or None,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid lead-form configuration.") from exc


def _load_form(form_id: str) -> LeadFormConfig:
    try:
        return _forms().load_form(form_id)
    except LeadStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _load_lead(lead_id: str) -> AuditLead:
    try:
        return _leads().load_lead(lead_id)
    except LeadStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _origin(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    origin = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port is not None:
        origin += f":{parsed.port}"
    return origin


def _request_origin(request: Request) -> str | None:
    return _origin(request.headers.get("origin")) or _origin(request.headers.get("referer"))


def _enforce_origin(request: Request, config: LeadFormConfig) -> None:
    if not config.allowed_origins:
        return
    if _request_origin(request) not in config.allowed_origins:
        raise HTTPException(status_code=403, detail="This audit form is not enabled for this origin.")


def _enforce_rate_limit(request: Request, form_id: str) -> None:
    client = request.client.host if request.client is not None else "unknown"
    key = f"{form_id}:{client}"
    now = time.monotonic()
    bucket = _RATE_BUCKETS[key]
    while bucket and now - bucket[0] >= _RATE_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT:
        raise HTTPException(status_code=429, detail="This audit form has reached its temporary request limit.")
    bucket.append(now)


def _profile_options(selected: str | None) -> str:
    options = ["<option value=''>Default Veridra report</option>"]
    for entry in ProfileStore().list():
        label = entry.organisation_name
        if entry.client_name:
            label += f" — {entry.client_name}"
        options.append(
            "<option value='{identifier}'{selected}>{label}</option>".format(
                identifier=entry.id,
                selected=" selected" if entry.id == selected else "",
                label=html.escape(label),
            )
        )
    return "".join(options)


def _form_editor(config: LeadFormConfig | None = None) -> str:
    item = config or LeadFormConfig(
        organisation_label="Veridra Agency",
        consent_text="I agree that this organisation may contact me about this website audit.",
    )
    origins = "\n".join(item.allowed_origins)
    webhook_url = str(item.webhook_url) if item.webhook_url else ""
    return f"""<section><h1>Create embedded audit form</h1><p class='muted'>Saved only on this device. Optional signed HTTPS webhook delivery is immediate and best-effort; email, automatic retries and background workers are not included.</p><form method='post' action='/lead-forms'><div class='row'><div><label for='organisation_label'>Organisation label</label><input id='organisation_label' name='organisation_label' maxlength='120' required value='{html.escape(item.organisation_label, quote=True)}'></div><div><label for='heading'>Public heading</label><input id='heading' name='heading' maxlength='160' required value='{html.escape(item.heading, quote=True)}'></div></div><label for='introduction'>Introduction</label><textarea id='introduction' name='introduction' maxlength='1000'>{html.escape(item.introduction)}</textarea><div class='row'><div><label for='submit_label'>Submit-button label</label><input id='submit_label' name='submit_label' maxlength='80' required value='{html.escape(item.submit_label, quote=True)}'></div><div><label for='profile_id'>Report profile</label><select id='profile_id' name='profile_id'>{_profile_options(item.profile_id)}</select></div></div><label for='consent_text'>Required consent wording</label><textarea id='consent_text' name='consent_text' maxlength='1000' required>{html.escape(item.consent_text)}</textarea><label for='allowed_origins'>Allowed embedding origins, one per line</label><textarea id='allowed_origins' name='allowed_origins' placeholder='https://agency.example'>{html.escape(origins)}</textarea><div class='row'><div><label for='webhook_url'>HTTPS webhook URL</label><input id='webhook_url' name='webhook_url' maxlength='2048' placeholder='https://automation.example/veridra' value='{html.escape(webhook_url, quote=True)}'></div><div><label for='webhook_secret'>Webhook signing secret</label><input id='webhook_secret' name='webhook_secret' type='password' minlength='16' maxlength='256' value='{html.escape(item.webhook_secret or "", quote=True)}'></div></div><p><label class='check'><input type='checkbox' name='collect_company'{' checked' if item.collect_company else ''}> Collect company</label><label class='check'><input type='checkbox' name='collect_phone'{' checked' if item.collect_phone else ''}> Collect phone</label></p><button type='submit'>Save lead form</button></form></section>"""


def _public_form(form_id: str, config: LeadFormConfig) -> str:
    company = "<label for='company'>Company</label><input id='company' name='company' maxlength='160'>" if config.collect_company else ""
    phone = "<label for='phone'>Phone</label><input id='phone' name='phone' maxlength='80'>" if config.collect_phone else ""
    return f"""<section><p class='muted'>{html.escape(config.organisation_label)}</p><h1>{html.escape(config.heading)}</h1><p>{html.escape(config.introduction)}</p><form method='post' action='/embed/audit/{form_id}'><label for='website'>Website</label><input id='website' name='website' maxlength='2048' placeholder='example.com' required><div class='row'><div><label for='name'>Name</label><input id='name' name='name' maxlength='160' required></div><div><label for='email'>Email</label><input id='email' name='email' type='email' maxlength='320' required></div></div><div class='row'><div>{company}</div><div>{phone}</div></div><label class='check' for='consent'><input id='consent' name='consent' type='checkbox' value='yes' required><span>{html.escape(config.consent_text)}</span></label><p><button type='submit'>{html.escape(config.submit_label)}</button></p></form><p class='muted'>This performs bounded public checks. It is not a penetration test.</p></section>"""


def _delivery_rows(lead_id: str) -> str:
    rows = "".join(
        "<tr><td>{number}</td><td>{status}</td><td>{code}</td><td>{time}</td><td>{error}</td></tr>".format(
            number=attempt.attempt_number,
            status=html.escape(attempt.status.value),
            code=attempt.status_code or "—",
            time=html.escape(attempt.attempted_at.isoformat()),
            error=html.escape(attempt.error or "—"),
        )
        for _, attempt in _deliveries().list_for_lead(lead_id)
    )
    return rows or "<tr><td colspan='5'>No webhook delivery has been attempted.</td></tr>"


@router.get("/lead-forms", response_class=HTMLResponse)
def lead_form_index() -> str:
    rows = "".join(
        "<tr><td><strong>{organisation}</strong><br>{heading}</td><td><code>{identifier}</code></td><td><div class='actions'><a class='button' href='/lead-forms/{identifier}'>Open</a><a class='button secondary' href='/embed/audit/{identifier}'>Preview public form</a><form class='inline' method='post' action='/lead-forms/{identifier}/delete'><button class='danger' type='submit'>Delete</button></form></div></td></tr>".format(
            organisation=html.escape(config.organisation_label),
            heading=html.escape(config.heading),
            identifier=identifier,
        )
        for identifier, model in _forms().list()
        if (config := LeadFormConfig.model_validate(model))
    ) or "<tr><td colspan='3'>No lead forms have been saved.</td></tr>"
    body = _form_editor() + f"""<section><h2>Saved lead forms</h2><table><thead><tr><th>Form</th><th>ID</th><th>Actions</th></tr></thead><tbody>{rows}</tbody></table></section>"""
    return _page("Lead forms", body)


@router.post("/lead-forms")
async def save_lead_form(request: Request) -> RedirectResponse:
    identifier = _forms().save(_parse_form_config(await request.body()))
    return RedirectResponse(f"/lead-forms/{identifier}", status_code=303)


@router.get("/lead-forms/{form_id}", response_class=HTMLResponse)
def lead_form_detail(form_id: str) -> str:
    config = _load_form(form_id)
    origins = ", ".join(config.allowed_origins) or "Any origin during loopback evaluation"
    webhook = str(config.webhook_url) if config.webhook_url else "Disabled"
    body = f"""<section><h1>{html.escape(config.organisation_label)}</h1><p><strong>Heading:</strong> {html.escape(config.heading)}<br><strong>Allowed origins:</strong> {html.escape(origins)}<br><strong>Report profile:</strong> {html.escape(config.profile_id or 'Default Veridra')}<br><strong>Webhook:</strong> {html.escape(webhook)}<br><strong>Webhook signing:</strong> {'Enabled' if config.webhook_secret else 'Disabled'}</p><div class='actions'><a class='button' href='/embed/audit/{form_id}'>Preview public form</a><a class='button secondary' href='/leads?form={form_id}'>View captured leads</a><a class='button secondary' href='/lead-forms'>Back</a></div></section><section><h2>Embed</h2><p class='muted'>Use an iframe only after deploying behind authentication-aware administration and production abuse controls.</p><pre>&lt;iframe src=&quot;/embed/audit/{form_id}&quot; title=&quot;Website audit&quot;&gt;&lt;/iframe&gt;</pre></section>"""
    return _page("Lead form", body)


@router.post("/lead-forms/{form_id}/delete")
def delete_lead_form(form_id: str) -> RedirectResponse:
    try:
        _forms().delete(form_id)
    except LeadStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse("/lead-forms", status_code=303)


@router.get("/embed/audit/{form_id}", response_class=HTMLResponse)
def embedded_audit_form(form_id: str, request: Request) -> str:
    config = _load_form(form_id)
    _enforce_origin(request, config)
    return _page(config.heading, _public_form(form_id, config), public=True)


@router.post("/embed/audit/{form_id}", response_class=HTMLResponse)
async def submit_embedded_audit(form_id: str, request: Request) -> str:
    config = _load_form(form_id)
    _enforce_origin(request, config)
    _enforce_rate_limit(request, form_id)
    body = await request.body()
    if _single(body, "consent") != "yes":
        raise HTTPException(status_code=400, detail="Explicit consent is required.")
    try:
        assessment = assess_url(_single(body, "website"))
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assessment_id = _history().save(assessment)
    try:
        lead = AuditLead(
            form_id=form_id,
            website=assessment.target,
            name=_single(body, "name"),
            email=_single(body, "email"),
            company=_single(body, "company") if config.collect_company else "",
            phone=_single(body, "phone") if config.collect_phone else "",
            consent_text=config.consent_text,
            consented_at=consent_timestamp(),
            assessment_id=assessment_id,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid lead submission.") from exc
    lead_id = _leads().save(lead)
    await deliver_lead_webhook(
        lead_id=lead_id,
        lead=lead,
        assessment=assessment,
        config=config,
    )
    metrics = "".join(
        f"<article class='metric'><span>{html.escape(key.title())}</span><strong>{value}</strong></article>"
        for key, value in assessment.summary.items()
    )
    body_html = f"""<section><p class='muted'>{html.escape(config.organisation_label)}</p><h1>Your website assessment is ready</h1><p>Thank you, {html.escape(lead.name)}. The bounded assessment completed successfully.</p><div class='metrics'>{metrics}</div><p class='muted'>The organisation may contact you under the consent wording shown in the form. This result is not a penetration test.</p></section>"""
    return _page("Assessment complete", body_html, public=True)


@router.get("/leads", response_class=HTMLResponse)
def lead_index(status: str | None = Query(default=None), form: str | None = Query(default=None)) -> str:
    selected: LeadStatus | None = None
    if status:
        try:
            selected = LeadStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Unknown lead status.") from exc
    if form is not None:
        _load_form(form)
    filters = " ".join(
        ["<a class='button secondary' href='/leads'>All</a>"]
        + [
            f"<a class='button secondary' href='/leads?status={item.value}'>{html.escape(item.value.title())}</a>"
            for item in LeadStatus
        ]
    )
    rows = "".join(
        "<tr><td><strong>{name}</strong><br>{email}</td><td>{website}</td><td>{status}</td><td>{date}</td><td><a class='button secondary' href='/leads/{identifier}'>Open</a></td></tr>".format(
            name=html.escape(lead.name),
            email=html.escape(str(lead.email)),
            website=html.escape(str(lead.website)),
            status=html.escape(lead.status.value),
            date=html.escape(lead.consented_at.isoformat()),
            identifier=identifier,
        )
        for identifier, lead in _leads().list_leads(form_id=form, status=selected)
    ) or "<tr><td colspan='5'>No leads match this view.</td></tr>"
    body = f"""<section><h1>Captured audit leads</h1><p class='muted'>Local operator-controlled records with optional immediate signed webhook delivery. No email, CRM adapter or automatic retry worker is active.</p><div class='actions'>{filters}<a class='button' href='/leads.csv'>Export CSV</a></div></section><section><table><thead><tr><th>Lead</th><th>Website</th><th>Status</th><th>Consent time</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></section>"""
    return _page("Leads", body)


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail(lead_id: str) -> str:
    lead = _load_lead(lead_id)
    config = _load_form(lead.form_id)
    options = "".join(
        "<option value='{value}'{selected}>{label}</option>".format(
            value=item.value,
            selected=" selected" if item == lead.status else "",
            label=html.escape(item.value.replace("_", " ").title()),
        )
        for item in LeadStatus
    )
    retry = (
        f"<form method='post' action='/leads/{lead_id}/delivery/retry'><button class='secondary' type='submit'>Retry webhook now</button></form>"
        if config.webhook_url
        else "<p class='muted'>Webhook delivery is disabled for this lead form.</p>"
    )
    body = f"""<section><h1>{html.escape(lead.name)}</h1><p><strong>Email:</strong> {html.escape(str(lead.email))}<br><strong>Website:</strong> {html.escape(str(lead.website))}<br><strong>Company:</strong> {html.escape(lead.company or 'Not supplied')}<br><strong>Phone:</strong> {html.escape(lead.phone or 'Not supplied')}<br><strong>Consent:</strong> {html.escape(lead.consent_text)}<br><strong>Consented at:</strong> {html.escape(lead.consented_at.isoformat())}<br><strong>Assessment:</strong> <a href='/history/{lead.assessment_id}'><code>{lead.assessment_id}</code></a></p></section><section><h2>Webhook delivery</h2>{retry}<table><thead><tr><th>Attempt</th><th>Status</th><th>HTTP</th><th>Time</th><th>Error</th></tr></thead><tbody>{_delivery_rows(lead_id)}</tbody></table></section><section><h2>Manage lead</h2><form method='post' action='/leads/{lead_id}/edit'><label for='status'>Status</label><select id='status' name='status'>{options}</select><label for='notes'>Notes</label><textarea id='notes' name='notes' maxlength='5000'>{html.escape(lead.notes)}</textarea><p><button type='submit'>Save changes</button></p></form><form method='post' action='/leads/{lead_id}/delete'><button class='danger' type='submit'>Delete lead</button></form></section>"""
    return _page("Lead detail", body)


@router.post("/leads/{lead_id}/delivery/retry")
async def retry_lead_delivery(lead_id: str) -> RedirectResponse:
    lead = _load_lead(lead_id)
    config = _load_form(lead.form_id)
    if config.webhook_url is None:
        raise HTTPException(status_code=400, detail="Webhook delivery is not configured for this form.")
    try:
        assessment = _history().load(lead.assessment_id)
    except HistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await deliver_lead_webhook(
        lead_id=lead_id,
        lead=lead,
        assessment=assessment,
        config=config,
    )
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/edit")
async def edit_lead(lead_id: str, request: Request) -> RedirectResponse:
    lead = _load_lead(lead_id)
    body = await request.body()
    try:
        updated = AuditLead.model_validate(
            lead.model_copy(
                update={
                    "status": LeadStatus(_single(body, "status")),
                    "notes": _single(body, "notes"),
                }
            )
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid lead update.") from exc
    try:
        new_id = _leads().replace(lead_id, updated)
    except LeadStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(f"/leads/{new_id}", status_code=303)


@router.post("/leads/{lead_id}/delete")
def delete_lead(lead_id: str) -> RedirectResponse:
    try:
        _leads().delete(lead_id)
    except LeadStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse("/leads", status_code=303)


@router.get("/leads.csv")
def export_leads_csv() -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "form_id",
            "website",
            "name",
            "email",
            "company",
            "phone",
            "status",
            "consented_at",
            "assessment_id",
            "notes",
        ]
    )
    for identifier, lead in _leads().list_leads():
        writer.writerow(
            [
                identifier,
                lead.form_id,
                str(lead.website),
                lead.name,
                str(lead.email),
                lead.company,
                lead.phone,
                lead.status.value,
                lead.consented_at.isoformat(),
                lead.assessment_id,
                lead.notes,
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=veridra-leads.csv"},
    )
