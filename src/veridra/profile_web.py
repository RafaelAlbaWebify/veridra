from __future__ import annotations

import html
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .profile_store import ProfileStore, ProfileStoreError
from .report_profiles import ReportProfile

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _store() -> ProfileStore:
    return ProfileStore()


def _page(body: str, *, title: str = "Report profiles") -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:980px;margin:36px auto;padding:0 20px}}section{{background:white;border:1px solid #dfe3e8;border-radius:9px;padding:22px;margin-bottom:18px}}label{{display:block;font-weight:700;margin:13px 0 5px}}input,textarea,select{{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}}textarea{{min-height:90px}}button,.button{{display:inline-block;border:0;border-radius:7px;background:#22272d;color:white;padding:10px 15px;text-decoration:none;cursor:pointer}}.secondary{{background:#5f6873}}.danger{{background:#b42318}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}}.muted{{color:#68707a}}.actions{{display:flex;gap:8px;flex-wrap:wrap}}@media(max-width:700px){{.row{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}</style></head><body><main>{body}</main></body></html>"""


def _profile_form(
    profile: ReportProfile | None = None,
    *,
    action: str = "/profiles",
    heading: str = "Create report profile",
    button_label: str = "Save profile locally",
) -> str:
    item = profile or ReportProfile()
    checked = " checked" if item.show_raw_evidence else ""
    return f"""<section><h1>{html.escape(heading)}</h1><p class='muted'>Profiles are saved only on this device and only after submission.</p><form method='post' action='{html.escape(action, quote=True)}'><div class='row'><div><label for='organisation_name'>Organisation</label><input id='organisation_name' name='organisation_name' maxlength='120' required value='{html.escape(item.organisation_name, quote=True)}'></div><div><label for='client_name'>Client</label><input id='client_name' name='client_name' maxlength='120' value='{html.escape(item.client_name or '', quote=True)}'></div></div><div class='row'><div><label for='consultant_name'>Consultant</label><input id='consultant_name' name='consultant_name' maxlength='120' value='{html.escape(item.consultant_name or '', quote=True)}'></div><div><label for='accent_colour'>Accent colour</label><input id='accent_colour' name='accent_colour' pattern='#[0-9A-Fa-f]{{6}}' required value='{html.escape(item.accent_colour, quote=True)}'></div></div><label for='introduction'>Introduction</label><textarea id='introduction' name='introduction' maxlength='1200'>{html.escape(item.introduction or '')}</textarea><div class='row'><div><label for='call_to_action_label'>Call-to-action label</label><input id='call_to_action_label' name='call_to_action_label' maxlength='80' value='{html.escape(item.call_to_action_label or '', quote=True)}'></div><div><label for='call_to_action_url'>Call-to-action URL</label><input id='call_to_action_url' name='call_to_action_url' maxlength='2048' value='{html.escape(item.call_to_action_url or '', quote=True)}'></div></div><div class='row'><div><label for='language'>Language</label><select id='language' name='language'><option value='en'{' selected' if item.language == 'en' else ''}>English</option><option value='es'{' selected' if item.language == 'es' else ''}>Spanish</option></select></div><div><label for='show_raw_evidence'>Evidence</label><label><input style='width:auto' id='show_raw_evidence' name='show_raw_evidence' type='checkbox' value='true'{checked}> Include raw evidence</label></div></div><p><button type='submit'>{html.escape(button_label)}</button> <a class='button secondary' href='/profiles'>Back to profiles</a></p></form></section>"""


async def _profile_from_request(request: Request) -> ReportProfile:
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)

    def value(name: str) -> str | None:
        raw = values.get(name, [""])[0].strip()
        return raw or None

    try:
        return ReportProfile(
            organisation_name=value("organisation_name") or "Veridra",
            client_name=value("client_name"),
            consultant_name=value("consultant_name"),
            accent_colour=value("accent_colour") or "#22272d",
            introduction=value("introduction"),
            call_to_action_label=value("call_to_action_label"),
            call_to_action_url=value("call_to_action_url"),
            language=value("language") or "en",
            show_raw_evidence=value("show_raw_evidence") == "true",
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
    details = f"""<section><h1>{html.escape(profile.organisation_name)}</h1><p><strong>Client:</strong> {html.escape(profile.client_name or 'Not set')}</p><p><strong>Consultant:</strong> {html.escape(profile.consultant_name or 'Not set')}</p><p><strong>Language:</strong> {html.escape(profile.language)}</p><p><strong>Accent:</strong> {html.escape(profile.accent_colour)}</p><p><strong>Raw evidence:</strong> {'Included' if profile.show_raw_evidence else 'Hidden'}</p><div class='actions'><a class='button' href='/report?demo=true&amp;profile={entry_id}'>Preview demo report</a><a class='button secondary' href='/export?demo=true&amp;profile={entry_id}'>Export demo evidence</a><a class='button secondary' href='/profiles/{entry_id}/edit'>Edit profile</a><a class='button secondary' href='/profiles'>Back</a></div></section><section><h2>Launch branded assessment</h2><p class='muted'>Enter a public website to generate a report or evidence package with this profile.</p><form method='get'><input type='hidden' name='profile' value='{entry_id}'><label for='target_url'>Public website</label><input id='target_url' name='url' maxlength='2048' placeholder='example.com' required><p class='actions'><button type='submit' formaction='/report'>Open report</button><button class='secondary' type='submit' formaction='/export'>Export evidence</button></p></form></section>"""
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
