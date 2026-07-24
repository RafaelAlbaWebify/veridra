# ruff: noqa: E501
from __future__ import annotations

import html
from datetime import UTC, datetime
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .lead_store import AuditLead, LeadStore, LeadStoreError
from .member_references import MemberReferenceError, member_reference_label, require_active_member
from .project_store import ClientProject, ProjectStore, ProjectStoreError
from .task_store import RemediationTask, TaskStore, TaskStoreError
from .workspace_members import AuditEvent, AuditTrailStore, MemberStore

router = APIRouter(prefix="/assignments", tags=["member assignments"])


def _page(body: str) -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Local assignments</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:1180px;margin:36px auto;padding:0 20px}}section{{background:#fff;border:1px solid #dfe3e8;border-radius:9px;padding:22px;margin-bottom:18px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}}input,select{{width:100%;padding:8px;border:1px solid #cfd4da;border-radius:6px}}button,.button{{display:inline-block;border:0;border-radius:6px;background:#22272d;color:#fff;padding:9px 12px;text-decoration:none;cursor:pointer}}.muted{{color:#68707a}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}@media(max-width:760px){{table{{display:block;overflow:auto}}.row{{grid-template-columns:1fr}}}}</style></head><body><main>{body}</main></body></html>"""


def _active_member_options(selected: str | None) -> str:
    options = ["<option value=''>Use legacy text only</option>"]
    for member in MemberStore().list():
        if not member.active:
            continue
        options.append(
            "<option value='{identifier}'{selected}>{label} — {role}</option>".format(
                identifier=html.escape(member.id, quote=True),
                selected=" selected" if member.id == selected else "",
                label=html.escape(member.display_name),
                role=html.escape(member.role.value),
            )
        )
    return "".join(options)


def _values(body: bytes) -> tuple[str | None, str]:
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    member_id = parsed.get("member_id", [""])[0].strip() or None
    legacy_label = parsed.get("legacy_label", [""])[0].strip()
    try:
        return require_active_member(member_id), legacy_label
    except MemberReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _record(action: str, subject_type: str, subject_id: str, detail: str) -> None:
    AuditTrailStore().record(
        AuditEvent(
            action=action,
            occurred_at=datetime.now(UTC),
            subject_type=subject_type,
            subject_id=subject_id,
            detail=detail,
        )
    )


def _project_rows() -> str:
    rows: list[str] = []
    store = ProjectStore()
    for entry in store.list():
        project = store.load(entry.id)
        current = member_reference_label(project.contact_member_id, project.contact_label)
        rows.append(
            "<tr><td><strong>{name}</strong><br><span class='muted'>{current}</span></td><td><form method='post' action='/assignments/projects/{identifier}'><div class='row'><select name='member_id'>{options}</select><input name='legacy_label' maxlength='120' value='{legacy}' placeholder='Legacy contact label'></div><p><button type='submit'>Save contact</button></p></form></td></tr>".format(
                name=html.escape(project.name),
                current=html.escape(current or "Unassigned"),
                identifier=html.escape(entry.id, quote=True),
                options=_active_member_options(project.contact_member_id),
                legacy=html.escape(project.contact_label or "", quote=True),
            )
        )
    return "".join(rows) or "<tr><td colspan='2'>No projects are available.</td></tr>"


def _lead_rows() -> str:
    rows: list[str] = []
    for identifier, lead in LeadStore().list_leads():
        current = member_reference_label(lead.assigned_owner_member_id, lead.assigned_owner)
        rows.append(
            "<tr><td><strong>{name}</strong><br><span class='muted'>{current}</span></td><td><form method='post' action='/assignments/leads/{identifier}'><div class='row'><select name='member_id'>{options}</select><input name='legacy_label' maxlength='120' value='{legacy}' placeholder='Legacy owner label'></div><p><button type='submit'>Save owner</button></p></form></td></tr>".format(
                name=html.escape(lead.name),
                current=html.escape(current or "Unassigned"),
                identifier=html.escape(identifier, quote=True),
                options=_active_member_options(lead.assigned_owner_member_id),
                legacy=html.escape(lead.assigned_owner, quote=True),
            )
        )
    return "".join(rows) or "<tr><td colspan='2'>No leads are available.</td></tr>"


def _task_rows() -> str:
    rows: list[str] = []
    for identifier, task in TaskStore().list():
        current = member_reference_label(task.owner_member_id, task.owner_label)
        rows.append(
            "<tr><td><strong>{title}</strong><br><span class='muted'>{current}</span></td><td><form method='post' action='/assignments/tasks/{identifier}'><div class='row'><select name='member_id'>{options}</select><input name='legacy_label' maxlength='120' value='{legacy}' placeholder='Legacy owner label'></div><p><button type='submit'>Save owner</button></p></form></td></tr>".format(
                title=html.escape(task.title),
                current=html.escape(current or "Unassigned"),
                identifier=html.escape(identifier, quote=True),
                options=_active_member_options(task.owner_member_id),
                legacy=html.escape(task.owner_label, quote=True),
            )
        )
    return "".join(rows) or "<tr><td colspan='2'>No tasks are available.</td></tr>"


@router.get("", response_class=HTMLResponse)
def assignment_dashboard() -> str:
    body = """<section><h1>Local member assignments</h1><p class='muted'>Assignments use active local member records for operational planning only. They do not authenticate users or authorize requests.</p><p><a class='button' href='/members'>Manage members</a></p></section>"""
    body += f"<section><h2>Project contacts</h2><table><thead><tr><th>Project</th><th>Assignment</th></tr></thead><tbody>{_project_rows()}</tbody></table></section>"
    body += f"<section><h2>Lead owners</h2><table><thead><tr><th>Lead</th><th>Assignment</th></tr></thead><tbody>{_lead_rows()}</tbody></table></section>"
    body += f"<section><h2>Task owners</h2><table><thead><tr><th>Task</th><th>Assignment</th></tr></thead><tbody>{_task_rows()}</tbody></table></section>"
    return _page(body)


@router.post("/projects/{project_id}")
async def assign_project(project_id: str, request: Request) -> RedirectResponse:
    member_id, legacy_label = _values(await request.body())
    store = ProjectStore()
    try:
        project = store.load(project_id)
        updated = ClientProject.model_validate(project.model_copy(update={"contact_member_id": member_id, "contact_label": legacy_label or None}))
        new_id = store.replace(project_id, updated)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record("project.contact.assigned", "project", new_id, member_id or legacy_label)
    return RedirectResponse("/assignments", status_code=303)


@router.post("/leads/{lead_id}")
async def assign_lead(lead_id: str, request: Request) -> RedirectResponse:
    member_id, legacy_label = _values(await request.body())
    store = LeadStore()
    try:
        lead = store.load_lead(lead_id)
        updated = AuditLead.model_validate(lead.model_copy(update={"assigned_owner_member_id": member_id, "assigned_owner": legacy_label}))
        store.replace(lead_id, updated)
    except LeadStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record("lead.owner.assigned", "lead", lead_id, member_id or legacy_label)
    return RedirectResponse("/assignments", status_code=303)


@router.post("/tasks/{task_id}")
async def assign_task(task_id: str, request: Request) -> RedirectResponse:
    member_id, legacy_label = _values(await request.body())
    store = TaskStore()
    try:
        task = store.load(task_id)
        updated = RemediationTask.model_validate(task.model_copy(update={"owner_member_id": member_id, "owner_label": legacy_label}))
        new_id = store.replace(task_id, updated)
    except TaskStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record("task.owner.assigned", "task", new_id, member_id or legacy_label)
    return RedirectResponse("/assignments", status_code=303)
