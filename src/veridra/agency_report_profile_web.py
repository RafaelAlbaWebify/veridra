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
from .project_store import ClientProject
from .report_profiles import DEFAULT_REPORT_PROFILE, REPORT_SECTIONS, ReportProfile
from .request_security import require_request_identity
from .tenant_profile_store import TenantProfileStore, TenantProfileStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency", tags=["agency-report-profiles"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:980px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:100px}.checks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.checks label{font-weight:400;margin:0}.checks input{width:auto;margin-right:7px}.logo-state{margin:8px 0 0}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}@media(max-width:700px){.grid,.checks{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _selected_areas(values: dict[str, list[str]]) -> tuple[str, ...]:
    raw = _one(values, "selected_areas").replace(",", "\n")
    return tuple(dict.fromkeys(value.strip() for value in raw.splitlines() if value.strip()))


def _require(identity: RequestIdentity) -> None:
    try:
        require_tenant_capability(identity, TenantCapability.manage_reports)
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc


def _project(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
) -> tuple[TenantProjectStore, ClientProject]:
    projects = TenantProjectStore(_root(request))
    try:
        project = projects.load(identity, projects.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Report profile source not found.") from exc
    return projects, project


@router.get("/projects/{project_id}/reports/profile", response_class=HTMLResponse)
def project_report_profile(project_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    _require(identity)
    _, project = _project(request, identity, project_id)
    profiles = TenantProfileStore(_root(request)).list(identity)
    options = ["<option value=''>Default Veridra profile</option>"]
    for entry in profiles:
        selected = " selected" if entry.id == project.profile_id else ""
        label = entry.organisation_name + (f" — {entry.client_name}" if entry.client_name else "")
        options.append(f"<option value='{html.escape(entry.id, quote=True)}'{selected}>{html.escape(label)}</option>")
    checks = "".join(
        f"<label><input type='checkbox' name='sections' value='{html.escape(section, quote=True)}' checked>{html.escape(section.replace('_', ' ').title())}</label>"
        for section in REPORT_SECTIONS
    )
    current = "Default Veridra profile" if project.profile_id is None else project.profile_id
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects'>Client projects</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project overview</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}/reports'>Report hub</a></p><h1>Report profile for {html.escape(project.name)}</h1><p class='notice'><strong>Current profile:</strong> {html.escape(current)}. Opening this page changes nothing.</p><form method='post' action='/agency/projects/{html.escape(project_id, quote=True)}/reports/profile/select'><label for='profile_id'>Use an existing profile</label><select id='profile_id' name='profile_id'>{''.join(options)}</select><p><button type='submit'>Apply selected profile</button></p></form></section><section><h2>Create and apply a new tenant profile</h2><form id='report-profile-form' method='post' action='/agency/projects/{html.escape(project_id, quote=True)}/reports/profile/create'><div class='grid'><div><label for='organisation_name'>Organisation</label><input id='organisation_name' name='organisation_name' maxlength='120' required></div><div><label for='client_name'>Client</label><input id='client_name' name='client_name' maxlength='120' value='{html.escape(project.client_label or '', quote=True)}'></div><div><label for='consultant_name'>Consultant</label><input id='consultant_name' name='consultant_name' maxlength='120'></div><div><label for='agency_email'>Agency email</label><input id='agency_email' name='agency_email' maxlength='254'></div><div><label for='agency_phone'>Agency phone</label><input id='agency_phone' name='agency_phone' maxlength='80'></div><div><label for='agency_website'>Agency website</label><input id='agency_website' name='agency_website' maxlength='2048'></div><div><label for='language'>Language</label><select id='language' name='language'><option value='en'>English</option><option value='es'>Spanish</option></select></div><div><label for='accent_colour'>Accent colour</label><input id='accent_colour' name='accent_colour' value='#22272d' pattern='#[0-9A-Fa-f]{{6}}' required></div></div><label for='cover_title'>Cover title</label><input id='cover_title' name='cover_title' maxlength='180' placeholder='Optional custom report title'><label for='introduction'>Introduction</label><textarea id='introduction' name='introduction' maxlength='1200'></textarea><label for='executive_summary'>Executive summary</label><textarea id='executive_summary' name='executive_summary' maxlength='2000' placeholder='Leave blank to use the generated transparent summary'></textarea><label for='conclusion'>Conclusion</label><textarea id='conclusion' name='conclusion' maxlength='2000'></textarea><div class='grid'><div><label for='call_to_action_label'>CTA label</label><input id='call_to_action_label' name='call_to_action_label' maxlength='80'></div><div><label for='call_to_action_url'>CTA URL</label><input id='call_to_action_url' name='call_to_action_url' maxlength='2048'></div></div><label for='selected_areas'>Assessment areas to include</label><textarea id='selected_areas' name='selected_areas' placeholder='Optional. One area per line or comma-separated. Leave blank to include all areas.'></textarea><label for='logo_file'>Agency logo</label><input id='logo_file' type='file' accept='image/png,image/jpeg'><input id='logo_data_uri' name='logo_data_uri' type='hidden'><p id='logo_state' class='muted logo-state'>Optional PNG or JPEG, maximum 200 KB. The logo is embedded in the profile; it is not fetched remotely.</p><label><input type='checkbox' name='show_raw_evidence' value='yes' checked style='width:auto'> Show raw evidence</label><h3>Report sections</h3><div class='checks'>{checks}</div><p><button type='submit'>Create and apply profile</button> <a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/reports'>Cancel</a></p></form><script>(function(){{const input=document.getElementById('logo_file');const hidden=document.getElementById('logo_data_uri');const state=document.getElementById('logo_state');input.addEventListener('change',function(){{hidden.value='';const file=input.files&&input.files[0];if(!file){{state.textContent='Optional PNG or JPEG, maximum 200 KB. The logo is embedded in the profile; it is not fetched remotely.';return;}}if(!['image/png','image/jpeg'].includes(file.type)){{input.value='';state.textContent='Logo must be PNG or JPEG.';return;}}if(file.size>200000){{input.value='';state.textContent='Logo exceeds the 200 KB limit.';return;}}const reader=new FileReader();reader.onload=function(){{hidden.value=String(reader.result||'');state.textContent='Logo ready to embed.';}};reader.onerror=function(){{input.value='';hidden.value='';state.textContent='Logo could not be read.';}};reader.readAsDataURL(file);}});}})();</script></section>"""
    return _page("Project report profile", body)


@router.post("/projects/{project_id}/reports/profile/select")
async def select_project_report_profile(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require(identity)
    projects, project = _project(request, identity, project_id)
    values = _values(await request.body())
    profile_id = _one(values, "profile_id") or None
    if profile_id is not None:
        try:
            TenantProfileStore(_root(request)).load(identity, TenantProfileStore.ref(identity, profile_id))
        except TenantProfileStoreError as exc:
            raise HTTPException(status_code=404, detail="Report profile source not found.") from exc
    replacement = project.model_copy(update={"profile_id": profile_id})
    try:
        projects.replace(identity, projects.ref(identity, project_id), replacement)
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Report profile source not found.") from exc
    return RedirectResponse(f"/agency/projects/{project_id}/reports?{urlencode({'profile': 'updated'})}", status_code=303)


@router.post("/projects/{project_id}/reports/profile/create")
async def create_project_report_profile(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require(identity)
    projects, project = _project(request, identity, project_id)
    values = _values(await request.body())
    sections = tuple(values.get("sections", [])) or DEFAULT_REPORT_PROFILE.section_order
    try:
        profile = ReportProfile(
            organisation_name=_one(values, "organisation_name"),
            client_name=_one(values, "client_name") or None,
            consultant_name=_one(values, "consultant_name") or None,
            agency_email=_one(values, "agency_email") or None,
            agency_phone=_one(values, "agency_phone") or None,
            agency_website=_one(values, "agency_website") or None,
            accent_colour=_one(values, "accent_colour"),
            cover_title=_one(values, "cover_title") or None,
            introduction=_one(values, "introduction") or None,
            executive_summary=_one(values, "executive_summary") or None,
            conclusion=_one(values, "conclusion") or None,
            call_to_action_label=_one(values, "call_to_action_label") or None,
            call_to_action_url=_one(values, "call_to_action_url") or None,
            language=_one(values, "language"),
            show_raw_evidence=_one(values, "show_raw_evidence") == "yes",
            selected_areas=_selected_areas(values),
            section_order=sections,
            logo_data_uri=_one(values, "logo_data_uri") or None,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Report profile input is invalid.") from exc
    profiles = TenantProfileStore(_root(request))
    profile_id = profiles.save(identity, profile)
    replacement = project.model_copy(update={"profile_id": profile_id})
    try:
        projects.replace(identity, projects.ref(identity, project_id), replacement)
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Report profile source not found.") from exc
    return RedirectResponse(f"/agency/projects/{project_id}/reports?{urlencode({'profile': 'created'})}", status_code=303)
