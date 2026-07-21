from __future__ import annotations

import html
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .collector import CollectionError
from .core import UnsafeTargetError
from .history import Comparison, HistoryEntry, HistoryError, HistoryStore
from .profile_store import ProfileEntry, ProfileStore, ProfileStoreError
from .project_store import ClientProject, ProjectStore, ProjectStoreError
from .service import assess_url

router = APIRouter(prefix="/projects", tags=["projects"])


def _store() -> ProjectStore:
    return ProjectStore()


def _profile_store() -> ProfileStore:
    return ProfileStore()


def _history_store() -> HistoryStore:
    return HistoryStore()


def _page(body: str, *, title: str = "Client projects") -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:1100px;margin:36px auto;padding:0 20px}}section{{background:white;border:1px solid #dfe3e8;border-radius:9px;padding:22px;margin-bottom:18px}}label{{display:block;font-weight:700;margin:13px 0 5px}}input,select{{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}}button,.button{{display:inline-block;border:0;border-radius:7px;background:#22272d;color:white;padding:10px 15px;text-decoration:none;cursor:pointer}}.secondary{{background:#5f6873}}.danger{{background:#b42318}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top;overflow-wrap:anywhere}}.muted{{color:#68707a}}.actions{{display:flex;gap:8px;flex-wrap:wrap}}form.inline{{display:inline}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.card{{border:1px solid #dfe3e8;border-radius:8px;padding:16px}}.card strong{{display:block;font-size:26px;margin-top:8px}}@media(max-width:760px){{.row,.cards{{grid-template-columns:1fr 1fr}}table{{display:block;overflow:auto}}}}</style></head><body><main>{body}</main></body></html>"""


def _profile_options(entries: list[ProfileEntry], selected: str | None) -> str:
    options = ["<option value=''>Default Veridra report</option>"]
    options.extend(
        "<option value='{identifier}'{selected}>{label}</option>".format(
            identifier=html.escape(entry.id, quote=True),
            selected=" selected" if entry.id == selected else "",
            label=html.escape(
                f"{entry.organisation_name} — {entry.client_name}"
                if entry.client_name
                else entry.organisation_name
            ),
        )
        for entry in entries
    )
    return "".join(options)


def _project_form(
    project: ClientProject | None = None,
    *,
    action: str = "/projects",
    heading: str = "Create client project",
) -> str:
    name = html.escape(project.name if project else "", quote=True)
    target = html.escape(project.target_url if project else "", quote=True)
    client = html.escape(project.client_label or "", quote=True) if project else ""
    profiles = _profile_options(
        _profile_store().list(), project.profile_id if project else None
    )
    return f"""<section><h1>{html.escape(heading)}</h1><p class='muted'>Projects are saved only on this device and only after submission.</p><form method='post' action='{html.escape(action, quote=True)}'><div class='row'><div><label for='name'>Project name</label><input id='name' name='name' maxlength='120' required value='{name}'></div><div><label for='client_label'>Client label</label><input id='client_label' name='client_label' maxlength='120' value='{client}'></div></div><div class='row'><div><label for='target_url'>Public website</label><input id='target_url' name='target_url' maxlength='2048' required placeholder='example.com' value='{target}'></div><div><label for='profile_id'>Report profile</label><select id='profile_id' name='profile_id'>{profiles}</select></div></div><p><button type='submit'>Save project locally</button> <a class='button secondary' href='/'>Back to assessment</a></p></form></section>"""


def _values(request_body: bytes) -> dict[str, str | None]:
    parsed = parse_qs(request_body.decode("utf-8"), keep_blank_values=True)

    def value(name: str) -> str | None:
        raw = parsed.get(name, [""])[0].strip()
        return raw or None

    return {
        "name": value("name"),
        "target_url": value("target_url"),
        "client_label": value("client_label"),
        "profile_id": value("profile_id"),
    }


def _build_project(values: dict[str, str | None]) -> ClientProject:
    profile_id = values["profile_id"]
    if profile_id is not None:
        try:
            _profile_store().load(profile_id)
        except ProfileStoreError as exc:
            raise HTTPException(
                status_code=400, detail="Selected report profile was not found."
            ) from exc
    try:
        return ClientProject.build(
            name=values["name"] or "",
            target_url=values["target_url"] or "",
            client_label=values["client_label"],
            profile_id=profile_id,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid client project.") from exc


def _project_query(project: ClientProject) -> dict[str, str]:
    query = {"url": project.target_url}
    if project.profile_id is not None:
        query["profile"] = project.profile_id
    return query


def _load_project(entry_id: str) -> ClientProject:
    try:
        return _store().load(entry_id)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _same_target(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _project_history(project: ClientProject) -> list[HistoryEntry]:
    return [
        entry
        for entry in _history_store().list()
        if _same_target(entry.target, project.target_url)
    ]


def _latest_comparison(entries: list[HistoryEntry]) -> Comparison | None:
    if len(entries) < 2:
        return None
    try:
        return _history_store().compare(entries[1].id, entries[0].id)
    except HistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _metric(label: str, value: int) -> str:
    return f"<article class='card'><span>{html.escape(label)}</span><strong>{value}</strong></article>"


def _timeline(entries: list[HistoryEntry]) -> str:
    if not entries:
        return "<tr><td colspan='4'>No project assessments have been saved yet.</td></tr>"
    return "".join(
        "<tr><td><a href='/history/{identifier}'><code>{identifier}</code></a></td><td>{generated}</td><td>{mode}</td><td>{total}</td></tr>".format(
            identifier=entry.id,
            generated=html.escape(entry.generated_at),
            mode=html.escape(entry.mode),
            total=entry.total_findings,
        )
        for entry in entries
    )


@router.get("", response_class=HTMLResponse)
def project_list() -> str:
    entries = _store().list()
    rows = "".join(
        "<tr><td><strong>{name}</strong><br><span class='muted'>{client}</span></td><td>{target}</td><td><div class='actions'><a class='button' href='/?{query}'>Assess</a><a class='button secondary' href='/projects/{identifier}/monitor'>Monitor</a><a class='button secondary' href='/projects/{identifier}'>Open</a><form class='inline' method='post' action='/projects/{identifier}/delete'><button class='danger' type='submit'>Delete</button></form></div></td></tr>".format(
            name=html.escape(entry.name),
            client=html.escape(entry.client_label or "No client label"),
            target=html.escape(entry.target_url),
            query=html.escape(
                urlencode(
                    {
                        "url": entry.target_url,
                        **({"profile": entry.profile_id} if entry.profile_id else {}),
                    }
                ),
                quote=True,
            ),
            identifier=entry.id,
        )
        for entry in entries
    ) or "<tr><td colspan='3' class='muted'>No client projects have been saved.</td></tr>"
    return _page(
        _project_form()
        + "<section><h2>Saved projects</h2><table><thead><tr><th>Project / client</th><th>Target</th><th>Actions</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></section>"
    )


@router.post("")
async def save_project(request: Request) -> RedirectResponse:
    project = _build_project(_values(await request.body()))
    entry_id = _store().save(project)
    return RedirectResponse(f"/projects/{entry_id}", status_code=303)


@router.post("/{entry_id}/monitor/run")
def run_project_assessment(entry_id: str) -> RedirectResponse:
    project = _load_project(entry_id)
    try:
        assessment = assess_url(project.target_url)
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _history_store().save(assessment)
    return RedirectResponse(f"/projects/{entry_id}/monitor", status_code=303)


@router.get("/{entry_id}/monitor", response_class=HTMLResponse)
def project_monitor(entry_id: str) -> str:
    project = _load_project(entry_id)
    entries = _project_history(project)
    comparison = _latest_comparison(entries)
    latest = entries[0] if entries else None
    previous = entries[1] if len(entries) > 1 else None
    if comparison is None:
        metrics = "".join(
            (
                _metric("Saved runs", len(entries)),
                _metric("Current findings", latest.total_findings if latest else 0),
                _metric("Resolved", 0),
                _metric("Changed", 0),
            )
        )
        comparison_note = "Run and save at least two distinct assessments to compare changes."
        compare_link = ""
    else:
        metrics = "".join(
            (
                _metric("Added", len(comparison.added)),
                _metric("Resolved", len(comparison.resolved)),
                _metric("Changed", len(comparison.changed)),
                _metric("Unchanged", len(comparison.unchanged)),
            )
        )
        comparison_note = "Latest assessment compared with the immediately preceding saved run."
        query = html.escape(
            urlencode({"before": comparison.before_id, "after": comparison.after_id}),
            quote=True,
        )
        compare_link = f"<a class='button secondary' href='/history/compare?{query}'>Open full comparison</a>"
    latest_text = html.escape(latest.generated_at) if latest else "Not yet assessed"
    previous_text = html.escape(previous.generated_at) if previous else "Not available"
    body = f"""<section><h1>{html.escape(project.name)}</h1><p><strong>Client:</strong> {html.escape(project.client_label or 'Not set')}<br><strong>Website:</strong> {html.escape(project.target_url)}<br><strong>Latest run:</strong> {latest_text}<br><strong>Previous run:</strong> {previous_text}</p><div class='actions'><form class='inline' method='post' action='/projects/{entry_id}/monitor/run'><button type='submit'>Run and save assessment</button></form>{compare_link}<a class='button secondary' href='/projects/{entry_id}'>Project details</a><a class='button secondary' href='/projects'>All projects</a></div></section><section><p class='muted'>{html.escape(comparison_note)}</p><div class='cards'>{metrics}</div></section><section><h2>Project run timeline</h2><table><thead><tr><th>Assessment</th><th>Generated</th><th>Mode</th><th>Findings</th></tr></thead><tbody>{_timeline(entries)}</tbody></table></section>"""
    return _page(body, title=f"{project.name} monitoring")


@router.get("/{entry_id}", response_class=HTMLResponse)
def project_detail(entry_id: str) -> str:
    project = _load_project(entry_id)
    query = urlencode(_project_query(project))
    details = f"""<section><h1>{html.escape(project.name)}</h1><p><strong>Client:</strong> {html.escape(project.client_label or 'Not set')}</p><p><strong>Website:</strong> {html.escape(project.target_url)}</p><p><strong>Report profile:</strong> {html.escape(project.profile_id or 'Default Veridra')}</p><div class='actions'><a class='button' href='/?{html.escape(query, quote=True)}'>Run assessment</a><a class='button' href='/projects/{entry_id}/monitor'>Monitor changes</a><a class='button secondary' href='/report?{html.escape(query, quote=True)}'>Open report</a><a class='button secondary' href='/export?{html.escape(query, quote=True)}'>Export evidence</a><form class='inline' method='post' action='/history/save?{html.escape(query, quote=True)}'><button type='submit'>Save assessment</button></form><a class='button secondary' href='/projects/{entry_id}/edit'>Edit</a><a class='button secondary' href='/projects'>Back</a></div></section>"""
    return _page(details, title=project.name)


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
def edit_project(entry_id: str) -> str:
    project = _load_project(entry_id)
    return _page(
        _project_form(
            project,
            action=f"/projects/{entry_id}/edit",
            heading="Edit client project",
        ),
        title=f"Edit {project.name}",
    )


@router.post("/{entry_id}/edit")
async def update_project(entry_id: str, request: Request) -> RedirectResponse:
    project = _build_project(_values(await request.body()))
    try:
        new_id = _store().replace(entry_id, project)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(f"/projects/{new_id}", status_code=303)


@router.post("/{entry_id}/delete")
def delete_project(entry_id: str) -> RedirectResponse:
    try:
        _store().delete(entry_id)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse("/projects", status_code=303)
