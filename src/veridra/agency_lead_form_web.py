# ruff: noqa: E501
from __future__ import annotations

import html
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
from .lead_form_tenant_binding import (
    LeadFormTenantBindingError,
    SQLiteLeadFormTenantBindingStore,
)
from .lead_store import LeadFormConfig
from .request_security import require_request_identity
from .runtime_config import RuntimeConfig, RuntimeEnvironment
from .tenant_entitlements import require_tenant_feature
from .tenant_lead_form_store import TenantLeadFormStore, TenantLeadFormStoreError
from .tenant_profile_store import TenantProfileStore, TenantProfileStoreError
from .tenant_workspace_policy import TenantWorkspacePolicy

router = APIRouter(prefix="/agency", tags=["agency-lead-forms"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1080px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.danger{background:#a23333}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:100px}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}code{overflow-wrap:anywhere}@media(max-width:760px){.grid{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _binding_store(request: Request) -> SQLiteLeadFormTenantBindingStore:
    database = getattr(request.app.state, "veridra_identity_database", None)
    if not isinstance(database, Path):
        raise HTTPException(status_code=503, detail="Tenant lead-form binding is not configured.")
    return SQLiteLeadFormTenantBindingStore(database)


def _require(identity: RequestIdentity) -> None:
    try:
        require_tenant_capability(identity, TenantCapability.manage_leads)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc


def _production_mode(request: Request) -> bool:
    config = getattr(request.app.state, "veridra_runtime_config", None)
    return (
        isinstance(config, RuntimeConfig)
        and config.environment is RuntimeEnvironment.production
    )


def _require_embedded_forms(
    request: Request,
    identity: RequestIdentity,
) -> None:
    if not _production_mode(request):
        return
    require_tenant_feature(
        TenantWorkspacePolicy(_root(request)),
        identity,
        "embedded_lead_forms",
    )


def _embedded_forms_allowed(
    request: Request,
    identity: RequestIdentity,
) -> bool:
    if not _production_mode(request):
        return True
    try:
        require_tenant_feature(
            TenantWorkspacePolicy(_root(request)),
            identity,
            "embedded_lead_forms",
        )
    except HTTPException:
        return False
    return True


def _public_origin(request: Request) -> str | None:
    config = getattr(request.app.state, "veridra_runtime_config", None)
    if not isinstance(config, RuntimeConfig) or config.trusted_origin is None:
        return None
    return config.trusted_origin.rstrip("/")


def _require_white_label_profile(
    request: Request,
    identity: RequestIdentity,
    profile_id: str | None,
) -> None:
    if profile_id is None or not _production_mode(request):
        return
    require_tenant_feature(
        TenantWorkspacePolicy(_root(request)),
        identity,
        "white_label",
    )


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _profile_options(request: Request, identity: RequestIdentity, selected: str | None) -> str:
    options = ["<option value=''>Default Veridra report</option>"]
    for entry in TenantProfileStore(_root(request)).list(identity):
        label = entry.organisation_name + (f" — {entry.client_name}" if entry.client_name else "")
        options.append(
            "<option value='{identifier}'{selected}>{label}</option>".format(
                identifier=html.escape(entry.id, quote=True),
                selected=" selected" if entry.id == selected else "",
                label=html.escape(label),
            )
        )
    return "".join(options)


def _origins(values: dict[str, list[str]]) -> tuple[str, ...]:
    raw = _one(values, "allowed_origins").replace(",", "\n")
    return tuple(value.strip() for value in raw.splitlines() if value.strip())


def _payload(
    request: Request,
    identity: RequestIdentity,
    values: dict[str, list[str]],
    *,
    current: LeadFormConfig | None = None,
) -> LeadFormConfig:
    profile_id = _one(values, "profile_id") or None
    _require_white_label_profile(request, identity, profile_id)
    if profile_id is not None:
        profiles = TenantProfileStore(_root(request))
        try:
            profiles.load(identity, profiles.ref(identity, profile_id))
        except TenantProfileStoreError as exc:
            raise HTTPException(status_code=400, detail="Selected report profile was not found.") from exc
    supplied_secret = _one(values, "webhook_secret")
    webhook_secret = supplied_secret or (current.webhook_secret if current else None)
    try:
        return LeadFormConfig(
            organisation_label=_one(values, "organisation_label"),
            heading=_one(values, "heading") or "Get your free website report",
            introduction=_one(values, "introduction"),
            submit_label=_one(values, "submit_label") or "Get my report",
            thank_you_message=(
                _one(values, "thank_you_message")
                or "Thank you. Your website assessment has been completed."
            ),
            consent_text=_one(values, "consent_text"),
            collect_company=_one(values, "collect_company") == "yes",
            collect_phone=_one(values, "collect_phone") == "yes",
            allowed_origins=_origins(values),
            profile_id=profile_id,
            webhook_url=_one(values, "webhook_url") or None,
            webhook_secret=webhook_secret,
            notification_email=_one(values, "notification_email") or None,
            cta_url=_one(values, "cta_url") or None,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Lead-form input is invalid.") from exc


def _form(
    request: Request,
    identity: RequestIdentity,
    *,
    action: str,
    submit_label: str,
    current: LeadFormConfig | None = None,
) -> str:
    item = current or LeadFormConfig(
        organisation_label="Veridra Agency",
        consent_text="I agree that this organisation may contact me about this website audit.",
    )
    origins = "\n".join(item.allowed_origins)
    secret_note = "Leave blank to keep the saved secret." if item.webhook_secret else "Optional; minimum 16 characters when supplied."
    return f"""<form method='post' action='{html.escape(action, quote=True)}'><div class='grid'><div><label for='organisation_label'>Organisation label</label><input id='organisation_label' name='organisation_label' maxlength='120' value='{html.escape(item.organisation_label, quote=True)}' required></div><div><label for='heading'>Public heading</label><input id='heading' name='heading' maxlength='160' value='{html.escape(item.heading, quote=True)}' required></div><div><label for='submit_label'>Submit button</label><input id='submit_label' name='submit_label' maxlength='80' value='{html.escape(item.submit_label, quote=True)}' required></div><div><label for='profile_id'>Report profile</label><select id='profile_id' name='profile_id'>{_profile_options(request, identity, item.profile_id)}</select></div></div><label for='introduction'>Introduction</label><textarea id='introduction' name='introduction' maxlength='1000'>{html.escape(item.introduction)}</textarea><label for='thank_you_message'>Thank-you message</label><textarea id='thank_you_message' name='thank_you_message' maxlength='1000' required>{html.escape(item.thank_you_message)}</textarea><label for='consent_text'>Required consent wording</label><textarea id='consent_text' name='consent_text' maxlength='1000' required>{html.escape(item.consent_text)}</textarea><label for='allowed_origins'>Allowed embedding origins</label><textarea id='allowed_origins' name='allowed_origins' placeholder='https://agency.example'>{html.escape(origins)}</textarea><div class='grid'><div><label for='notification_email'>Lead notification email</label><input id='notification_email' name='notification_email' type='email' maxlength='320' value='{html.escape(str(item.notification_email) if item.notification_email else "", quote=True)}'></div><div><label for='cta_url'>Completion CTA URL</label><input id='cta_url' name='cta_url' maxlength='2048' value='{html.escape(item.cta_url or "", quote=True)}'></div><div><label for='webhook_url'>HTTPS webhook URL</label><input id='webhook_url' name='webhook_url' maxlength='2048' value='{html.escape(item.webhook_url or "", quote=True)}'></div><div><label for='webhook_secret'>Webhook signing secret</label><input id='webhook_secret' name='webhook_secret' type='password' minlength='16' maxlength='256'><p class='muted'>{html.escape(secret_note)}</p></div></div><p><label><input type='checkbox' name='collect_company' value='yes'{' checked' if item.collect_company else ''} style='width:auto'> Collect company</label><label><input type='checkbox' name='collect_phone' value='yes'{' checked' if item.collect_phone else ''} style='width:auto'> Collect phone</label></p><p><button type='submit'>{html.escape(submit_label)}</button></p></form>"""


@router.get("/lead-forms", response_class=HTMLResponse)
def lead_form_index(request: Request, created: str | None = None, updated: str | None = None) -> str:
    identity = require_request_identity(request)
    _require(identity)
    feature_enabled = _embedded_forms_allowed(request, identity)
    store = TenantLeadFormStore(_root(request))
    rows: list[str] = []
    for form_id, form in store.list(identity):
        actions = (
            f"<a class='button' href='/embed/audit/{html.escape(form_id, quote=True)}'>Preview</a>"
            f"<a class='button secondary' href='/agency/lead-forms/{html.escape(form_id, quote=True)}/setup'>Setup</a>"
            f"<a class='button secondary' href='/agency/lead-forms/{html.escape(form_id, quote=True)}/edit'>Edit</a>"
            if feature_enabled
            else "<span class='muted'>Disabled by current plan</span>"
        )
        rows.append(
            f"<tr><td><strong>{html.escape(form.organisation_label)}</strong><br><span class='muted'>{html.escape(form.heading)}</span></td><td><code>{html.escape(form_id)}</code></td><td><div class='actions'>{actions}<form method='post' action='/agency/lead-forms/{html.escape(form_id, quote=True)}/delete'><button class='danger' type='submit'>Delete</button></form></div></td></tr>"
        )
    table = "".join(rows) or "<tr><td colspan='3'>No tenant lead forms have been created.</td></tr>"
    notice = ""
    if created:
        notice = "<p class='notice'><strong>Lead form created and tenant-bound.</strong></p>"
    elif updated:
        notice = "<p class='notice'><strong>Lead form updated.</strong></p>"
    if not feature_enabled:
        notice += (
            "<p class='notice'><strong>Embedded lead forms are disabled on the active plan.</strong> "
            "Existing forms are preserved but public capture is disabled. You can delete old forms "
            "or upgrade the workspace to create, edit and publish them again.</p>"
        )
    create_section = (
        f"<section><h2>Create lead form</h2>{_form(request, identity, action='/agency/lead-forms', submit_label='Create lead form')}</section>"
        if feature_enabled
        else ""
    )
    navigation = agency_navigation(identity, current="lead-forms")
    body = f"""{navigation}<section><p><a href='/agency'>Agency home</a></p><h1>Lead forms</h1><p class='muted'>Create tenant-owned embedded audit forms. Captured prospects enter this workspace’s lead list and can be converted into client projects.</p>{notice}</section>{create_section}<section><h2>Saved tenant lead forms</h2><table><thead><tr><th>Form</th><th>ID / embed path</th><th>Actions</th></tr></thead><tbody>{table}</tbody></table><p class='muted'>Public path: <code>/embed/audit/&lt;form-id&gt;</code>. Configure allowed origins before embedding on an external site.</p></section>"""
    return _page("Agency lead forms", body)


@router.get("/lead-forms/{form_id}/setup", response_class=HTMLResponse)
def lead_form_setup(form_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    _require(identity)
    _require_embedded_forms(request, identity)
    store = TenantLeadFormStore(_root(request))
    try:
        form = store.load(identity, store.ref(identity, form_id))
    except TenantLeadFormStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead form not found.") from exc
    binding = _binding_store(request).resolve(form_id)
    if binding is None or binding.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Lead form binding not found.")

    path = f"/embed/audit/{form_id}"
    origin = _public_origin(request)
    public_url = f"{origin}{path}" if origin is not None else path
    snippet = (
        f'<iframe src="{public_url}" title="Website audit" '
        'width="100%" height="720" loading="lazy"></iframe>'
    )
    origins = (
        ", ".join(form.allowed_origins)
        if form.allowed_origins
        else "Not restricted — add your agency website origin before public embedding."
    )
    origin_note = (
        ""
        if origin is not None
        else "<p class='notice'><strong>Public deployment origin is unavailable in this runtime.</strong> The relative path below becomes an absolute HTTPS URL in production.</p>"
    )
    navigation = agency_navigation(identity, current="lead-forms")
    body = f"""{navigation}<section><p><a href='/agency/lead-forms'>Lead forms</a> · <a href='/agency/lead-forms/{html.escape(form_id, quote=True)}/edit'>Edit form</a></p><h1>Embed setup</h1><p class='muted'>{html.escape(form.organisation_label)} · {html.escape(form.heading)}</p>{origin_note}</section><section><h2>1. Public form URL</h2><p><code>{html.escape(public_url)}</code></p><p><a class='button secondary' href='{html.escape(path, quote=True)}'>Preview form</a></p></section><section><h2>2. Allowed parent origins</h2><p>{html.escape(origins)}</p><p class='muted'>Use origins such as <code>https://agency.example</code>, without a path. These origins control which parent sites may load the form. The form postback itself is submitted to the trusted Veridra origin.</p></section><section><h2>3. Paste this iframe</h2><pre><code>{html.escape(snippet)}</code></pre><p class='muted'>Adjust height to fit your page. Keep the Veridra URL unchanged so tenant binding, rate limits, audit usage and lead attribution remain intact.</p></section><section><h2>4. Verify the flow</h2><ol><li>Open the page on one of the allowed parent origins.</li><li>Submit a test website and explicit consent.</li><li>Confirm the resulting prospect appears under <a href='/agency/leads'>Inbound leads</a> with this form as its source.</li></ol></section>"""
    return _page("Lead form embed setup", body)


@router.post("/lead-forms")
async def create_lead_form(request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require(identity)
    _require_embedded_forms(request, identity)
    form = _payload(request, identity, _values(await request.body()))
    store = TenantLeadFormStore(_root(request))
    binding_store = _binding_store(request)
    existing_ids = {form_id for form_id, _ in store.list(identity)}
    form_id = store.save(identity, form)
    try:
        binding_store.bind(
            form_id=form_id,
            tenant_id=identity.tenant_id,
            created_by_user_id=identity.user_id,
        )
    except LeadFormTenantBindingError as exc:
        if form_id not in existing_ids:
            try:
                store.delete(identity, store.ref(identity, form_id))
            except TenantLeadFormStoreError as rollback_exc:
                raise HTTPException(
                    status_code=500,
                    detail="Lead form binding failed and the new form could not be rolled back.",
                ) from rollback_exc
        raise HTTPException(status_code=409, detail="Lead form could not be tenant-bound.") from exc
    return RedirectResponse(f"/agency/lead-forms?{urlencode({'created': form_id})}", status_code=303)


@router.get("/lead-forms/{form_id}/edit", response_class=HTMLResponse)
def edit_lead_form(form_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    _require(identity)
    _require_embedded_forms(request, identity)
    store = TenantLeadFormStore(_root(request))
    try:
        current = store.load(identity, store.ref(identity, form_id))
    except TenantLeadFormStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead form not found.") from exc
    binding = _binding_store(request).resolve(form_id)
    if binding is None or binding.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Lead form binding not found.")
    navigation = agency_navigation(identity, current="lead-forms")
    body = f"""{navigation}<section><p><a href='/agency/lead-forms'>Lead forms</a></p><h1>Edit lead form</h1><p class='notice'><strong>Form ID:</strong> {html.escape(form_id)}. Saving updates this tenant-owned form in place.</p>{_form(request, identity, action=f'/agency/lead-forms/{form_id}/edit', submit_label='Save lead form', current=current)}</section>"""
    return _page("Edit lead form", body)


@router.post("/lead-forms/{form_id}/edit")
async def save_lead_form(form_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require(identity)
    _require_embedded_forms(request, identity)
    store = TenantLeadFormStore(_root(request))
    try:
        current = store.load(identity, store.ref(identity, form_id))
    except TenantLeadFormStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead form not found.") from exc
    binding = _binding_store(request).resolve(form_id)
    if binding is None or binding.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Lead form binding not found.")
    replacement = _payload(request, identity, _values(await request.body()), current=current)
    try:
        store.replace(identity, store.ref(identity, form_id), replacement)
    except TenantLeadFormStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead form not found.") from exc
    return RedirectResponse(f"/agency/lead-forms?{urlencode({'updated': form_id})}", status_code=303)


@router.post("/lead-forms/{form_id}/delete")
def delete_lead_form(form_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require(identity)
    store = TenantLeadFormStore(_root(request))
    binding_store = _binding_store(request)
    try:
        current = store.load(identity, store.ref(identity, form_id))
    except TenantLeadFormStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead form not found.") from exc
    binding = binding_store.resolve(form_id)
    if binding is None or binding.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Lead form binding not found.")
    try:
        store.delete(identity, store.ref(identity, form_id))
    except TenantLeadFormStoreError as exc:
        raise HTTPException(status_code=404, detail="Lead form not found.") from exc
    try:
        binding_store.unbind(form_id=form_id, tenant_id=identity.tenant_id)
    except LeadFormTenantBindingError as exc:
        restored_id = store.save(identity, current)
        if restored_id != form_id:
            raise HTTPException(
                status_code=500,
                detail="Lead form binding removal failed and form identity could not be restored.",
            ) from exc
        raise HTTPException(
            status_code=409,
            detail="Lead form binding could not be removed; the form was restored.",
        ) from exc
    return RedirectResponse("/agency/lead-forms", status_code=303)
