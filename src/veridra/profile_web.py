# ruff: noqa: E501
from __future__ import annotations

import html
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .profile_store import ProfileStore, ProfileStoreError
from .report_profiles import REPORT_SECTIONS, ReportProfile

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _store() -> ProfileStore:
    return ProfileStore()


def _page(body: str, *, title: str = "Report profiles") -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:1060px;margin:36px auto;padding:0 20px}}section{{background:white;border:1px solid #dfe3e8;border-radius:9px;padding:22px;margin-bottom:18px}}label{{display:block;font-weight:700;margin:13px 0 5px}}input,textarea,select{{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}}textarea{{min-height:90px}}button,.button{{display:inline-block;border:0;border-radius:7px;background:#22272d;color:white;padding:10px 15px;text-decoration:none;cursor:pointer}}.secondary{{background:#5f6873}}.danger{{background:#b42318}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}}.muted{{color:#68707a}}.actions{{display:flex;gap:8px;flex-wrap:wrap}}.check-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}.check-grid label{{margin:0;font-weight:400}}@media(max-width:700px){{.row,.check-grid{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}</style></head><body><main>{body}</main></body></html>"""


def _section_controls(item: ReportProfile) -> str:
    return "".join(
        "<label><input style='width:auto' type='checkbox' name='section' value='{value}'{checked}> {label}</label>".format(
            value=section,
            checked=" checked" if section in item.section_order else "",
            label=html.escape(section.replace("_", " ").title()),
        )
        for section in REPORT_SECTIONS
    )


def _profile_form(
    profile: ReportProfile | None = None,
    *,
    action: str = "/profiles",
    heading: str = "Create report profile",
    button_label: str = "Save profile locally",
) -> str:
    item = profile or ReportProfile()
    checked = " checked" if item.show_raw_evidence else ""
    selected_areas = ", ".join(item.selected_areas)
    section_order = ", ".join(item.section_order)
    return f"""<section><h1>{html.escape(heading)}</h1><p class='muted'>Profiles are saved only on this device. Embedded logos must be bounded PNG or JPEG data URIs; Veridra does not fetch remote branding assets.</p><form method='post' action='{html.escape(action, quote=True)}'>
<div class='row'><div><label for='organisation_name'>Organisation</label><input id='organisation_name' name='organisation_name' maxlength='120' required value='{html.escape(item.organisation_name, quote=True)}'></div><div><label for='client_name'>Client</label><input id='client_name' name='client_name' maxlength='120' value='{html.escape(item.client_name or '', quote=True)}'></div></div>
<div class='row'><div><label for='consultant_name'>Consultant</label><input id='consultant_name' name='consultant_name' maxlength='120' value='{html.escape(item.consultant_name or '', quote=True)}'></div><div><label for='accent_colour'>Accent colour</label><input id='accent_colour' name='accent_colour' pattern='#[0-9A-Fa-f]{{6}}' required value='{html.escape(item.accent_colour, quote=True)}'></div></div>
<div class='row'><div><label for='agency_email'>Agency email</label><input id='agency_email' name='agency_email' maxlength='254' value='{html.escape(item.agency_email or '', quote=True)}'></div><div><label for='agency_phone'>Agency phone</label><input id='agency_phone' name='agency_phone' maxlength='80' value='{html.escape(item.agency_phone or '', quote=True)}'></div></div>
<label for='agency_website'>Agency website</label><input id='agency_website' name='agency_website' maxlength='2048' value='{html.escape(item.agency_website or '', quote=True)}'>
<label for='cover_title'>Cover title</label><input id='cover_title' name='cover_title' maxlength='180' value='{html.escape(item.cover_title or '', quote=True)}'>
<label for='introduction'>Introduction</label><textarea id='introduction' name='introduction' maxlength='1200'>{html.escape(item.introduction or '')}</textarea>
<label for='executive_summary'>Custom executive summary</label><textarea id='executive_summary' name='executive_summary' maxlength='2000'>{html.escape(item.executive_summary or '')}</textarea>
<label for='conclusion'>Conclusion</label><textarea id='conclusion' name='conclusion' maxlength='2000'>{html.escape(item.conclusion or '')}</textarea>
<div class='row'><div><label for='call_to_action_label'>Call-to-action label</label><input id='call_to_action_label' name='call_to_action_label' maxlength='80' value='{html.escape(item.call_to_action_label or '', quote=True)}'></div><div><label for='call_to_action_url'>Call-to-action URL</label><input id='call_to_action_url' name='call_to_action_url' maxlength='2048' value='{html.escape(item.call_to_action_url or '', quote=True)}'></div></div>
<label for='selected_areas'>Included assessment areas</label><input id='selected_areas' name='selected_areas' maxlength='1000' placeholder='Leave blank for all; otherwise comma-separated exact area names' value='{html.escape(selected_areas, quote=True)}'>
<label>Enabled sections</label><div class='check-grid'>{_section_controls(item)}</div>
<label for='section_order'>Section order</label><input id='section_order' name='section_order' maxlength='500' value='{html.escape(section_order, quote=True)}'><p class='muted'>Comma-separated enabled section identifiers. Available: {html.escape(', '.join(REPORT_SECTIONS))}</p>
<label for='logo_data_uri'>Embedded logo data URI</label><textarea id='logo_data_uri' name='logo_data_uri' maxlength='275000' placeholder='data:image/png;base64,...'>{html.escape(item.logo_data_uri or '')}</textarea>
<div class='row'><div><label for='language'>Language</label><select id='language' name='language'><option value='en'{' selected' if item.language == 'en' else ''}>English</option><option value='es'{' selected' if item.language == 'es' else ''}>Spanish</option></select></div><div><label for='show_raw_evidence'>Evidence</label><label><input style='width:auto' id='show_raw_evidence' name='show_raw_evidence' type='checkbox' value='true'{checked}> Include raw evidence</label></div></div>
<p><button type='submit'>{html.escape(button_label)}</button> <a class='button secondary' href='/profiles'>Back to profiles</a></p></form></section>"""


async def _profile_from_request(request: Request) -> ReportProfile:
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)

    def value(name: str) -> str | None:
        raw = values.get(name, [""])[0].strip()
        return raw or None

    section_order_raw = value("section_order")
    selected_areas_raw = value("selected_areas")
    try:
        return ReportProfile.model_validate(
            {
                "organisation_name": value("organisation_name") or "Veridra",
                "client_name": value("client_name"),
                "consultant_name": value("consultant_name"),
                "agency_email": value("agency_email"),
                "agency_phone": value("agency_phone"),
                "agency_website": value("agency_website"),
                "accent_colour": value("accent_colour") or "#22272d",
                "cover_title": value("cover_title"),
                "introduction": value("introduction"),
                "executive_summary": value("executive_summary"),
                "conclusion": value("conclusion"),
                "call_to_action_label": value("call_to_action_label"),
                "call_to_action_url": value("call_to_action_url"),
                "language": value("language") or "en",
                "show_raw_evidence": value("show_raw_evidence") == "true",
                "selected_areas": tuple(
                    part.strip()
                    for part in (selected_areas_raw or "").split(",")
                    if part.strip()
                ),
                "section_order": tuple(
                    part.strip()
                    for part in (section_order_raw or "").split(",")
                    if part.strip()
                )
                or REPORT_SECTIONS,
                "logo_data_uri": value("logo_data_uri"),
            }
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid report profile.") from exc


@router.get("", response_class=HTMLResponse)
def profile_list() -> str:
    entries = _store().list()
    if entries:
        rows = "".join(
            "<tr><td><strong>{organisation}</strong><br><span class='muted'>{client}</span></td><td>{consultant}</td><td><div class='actions'><a class='button secondary' href='/profiles/{identifier}'>Review</a><a class='button secondary' href='/profiles/{identifier}/edit'>Edit</a><form method='post' action='/profiles/{identifier}/delete'><button class='danger' type='submit'>Delete</button></form></div></td></tr>".format(
                organisation=html.escape(entry.organisation_name),
                client=html.escape(entry.client_name or "No client"),
                consultant=html.escape(entry.consultant_name or "—"),
                identifier=entry.id,
            )
            for entry in entries
        )
    else:
        rows = "<tr><td colspan='3' class='muted'>No report profiles have been saved.</td></tr>"
    return _page(
        _profile_form()
        + "<section><h2>Saved profiles</h2><table><thead><tr><th>Organisation / client</th><th>Consultant</th><th>Actions</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></section>"
    )


@router.post("")
async def save_profile(request: Request) -> RedirectResponse:
    entry_id = _store().save(await _profile_from_request(request))
    return RedirectResponse(f"/profiles/{entry_id}", status_code=303)


@router.get("/{entry_id}", response_class=HTMLResponse)
def profile_detail(entry_id: str) -> str:
    try:
        profile = _store().load(entry_id)
    except ProfileStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    areas = ", ".join(profile.selected_areas) or "All areas"
    sections = ", ".join(profile.section_order)
    details = f"""<section><h1>{html.escape(profile.organisation_name)}</h1><p><strong>Client:</strong> {html.escape(profile.client_name or 'Not set')}</p><p><strong>Consultant:</strong> {html.escape(profile.consultant_name or 'Not set')}</p><p><strong>Agency contact:</strong> {html.escape(' · '.join(value for value in (profile.agency_email, profile.agency_phone, profile.agency_website) if value) or 'Not set')}</p><p><strong>Language:</strong> {html.escape(profile.language)}</p><p><strong>Accent:</strong> {html.escape(profile.accent_colour)}</p><p><strong>Areas:</strong> {html.escape(areas)}</p><p><strong>Sections:</strong> {html.escape(sections)}</p><p><strong>Embedded logo:</strong> {'Configured' if profile.logo_data_uri else 'Not set'}</p><p><strong>Raw evidence:</strong> {'Included' if profile.show_raw_evidence else 'Hidden'}</p><div class='actions'><a class='button' href='/report?demo=true&amp;profile={entry_id}'>Preview demo report</a><a class='button secondary' href='/export?demo=true&amp;profile={entry_id}'>Export demo evidence</a><a class='button secondary' href='/profiles/{entry_id}/edit'>Edit profile</a><a class='button secondary' href='/profiles'>Back</a></div></section><section><h2>Launch branded assessment</h2><p class='muted'>Enter a public website to generate a report or evidence package with this profile.</p><form method='get'><input type='hidden' name='profile' value='{entry_id}'><label for='target_url'>Public website</label><input id='target_url' name='url' maxlength='2048' placeholder='example.com' required><p class='actions'><button type='submit' formaction='/report'>Open report</button><button class='secondary' type='submit' formaction='/export'>Export evidence</button></p></form></section>"""
    return _page(details, title=profile.organisation_name)


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
def edit_profile(entry_id: str) -> str:
    try:
        profile = _store().load(entry_id)
    except ProfileStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _page(
        _profile_form(
            profile,
            action=f"/profiles/{entry_id}",
            heading="Edit report profile",
            button_label="Save changes",
        ),
        title=f"Edit {profile.organisation_name}",
    )


@router.post("/{entry_id}")
async def update_profile(entry_id: str, request: Request) -> RedirectResponse:
    try:
        replacement_id = _store().replace(entry_id, await _profile_from_request(request))
    except ProfileStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(f"/profiles/{replacement_id}", status_code=303)


@router.post("/{entry_id}/delete")
def delete_profile(entry_id: str) -> RedirectResponse:
    try:
        _store().delete(entry_id)
    except ProfileStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse("/profiles", status_code=303)
