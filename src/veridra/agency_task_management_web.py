# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qs

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
from .request_security import require_request_identity
from .task_store import RemediationTask, TaskStatus
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .tenant_task_store import TenantTaskStore, TenantTaskStoreError

router = APIRouter(prefix="/agency", tags=["agency-remediation-management"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1100px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.danger{background:#a23333}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.actions{display:flex;gap:8px;flex-wrap:wrap}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:120px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.pill{display:inline-block;border:1px solid #cfd4da;border-radius:999px;padding:3px 8px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}@media(max-width:760px){.row{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _one(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _require_manage_tasks(identity: RequestIdentity) -> None:
    try:
        require_tenant_capability(identity, TenantCapability.manage_tasks)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc


def _project(request: Request, identity: RequestIdentity, project_id: str) -> ClientProject:
    store = TenantProjectStore(_root(request))
    try:
        return store.load(identity, store.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


def _task(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
    task_id: str,
) -> RemediationTask:
    store = TenantTaskStore(_root(request))
    try:
        task = store.load(identity, store.ref(identity, task_id))
    except TenantTaskStoreError as exc:
        raise HTTPException(status_code=404, detail="Remediation task not found.") from exc
    if task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Remediation task not found.")
    return task


def _status_options(selected: TaskStatus) -> str:
    return "".join(
        "<option value='{value}'{selected}>{label}</option>".format(
            value=item.value,
            selected=" selected" if item == selected else "",
            label=html.escape(item.value.replace("_", " ").title()),
        )
        for item in TaskStatus
    )


@router.get("/projects/{project_id}/tasks", response_class=HTMLResponse)
def project_tasks(project_id: str, request: Request, status: str | None = None) -> str:
    identity = require_request_identity(request)
    _require_manage_tasks(identity)
    project = _project(request, identity, project_id)
    selected: TaskStatus | None = None
    if status:
        try:
            selected = TaskStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Unknown task status.") from exc
    entries = TenantTaskStore(_root(request)).list(
        identity,
        project_id=project_id,
        status=selected,
    )
    rows = "".join(
        f"<tr><td><strong>{html.escape(task.title)}</strong><br><code>{html.escape(task.finding_id)}</code></td><td><span class='pill'>{html.escape(task.status.value.replace('_', ' '))}</span></td><td>{html.escape(task.owner_label or 'Unassigned')}</td><td>{html.escape(task.due_date or 'Not set')}</td><td><a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/tasks/{html.escape(task_id, quote=True)}'>Open task</a></td></tr>"
        for task_id, task in entries
    ) or "<tr><td colspan='5'>No remediation tasks match this view.</td></tr>"
    filters = " ".join(
        [f"<a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/tasks'>All</a>"]
        + [
            f"<a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/tasks?status={item.value}'>{html.escape(item.value.replace('_', ' ').title())}</a>"
            for item in TaskStatus
        ]
    )
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects'>Client projects</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project overview</a></p><h1>{html.escape(project.name)} remediation tasks</h1><p class='notice'>Task status is an explicit operator decision. “Fixed” does not mean independently verified; use “verification required” and “verified” deliberately after checking evidence.</p><div class='actions'>{filters}</div></section><section><table><thead><tr><th>Task / finding</th><th>Status</th><th>Owner</th><th>Due</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></section>"""
    return _page("Remediation tasks", body)


@router.get("/projects/{project_id}/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(project_id: str, task_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    _require_manage_tasks(identity)
    project = _project(request, identity, project_id)
    task = _task(request, identity, project_id, task_id)
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects'>Client projects</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project overview</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}/tasks'>Remediation tasks</a></p><h1>{html.escape(task.title)}</h1><p><strong>Project:</strong> {html.escape(project.name)}<br><strong>Finding:</strong> {html.escape(task.finding_id)}<br><strong>Source assessment:</strong> <code>{html.escape(task.source_assessment_id)}</code></p><p class='notice'>Project, finding and source-assessment identity are immutable here. This page manages the work record only.</p></section><section><h2>Manage task</h2><form method='post' action='/agency/projects/{html.escape(project_id, quote=True)}/tasks/{html.escape(task_id, quote=True)}'><div class='row'><div><label for='status'>Status</label><select id='status' name='status'>{_status_options(task.status)}</select></div><div><label for='owner_label'>Owner</label><input id='owner_label' name='owner_label' maxlength='120' value='{html.escape(task.owner_label, quote=True)}'></div><div><label for='due_date'>Due date</label><input id='due_date' name='due_date' maxlength='40' value='{html.escape(task.due_date, quote=True)}'></div></div><label for='notes'>Notes</label><textarea id='notes' name='notes' maxlength='5000'>{html.escape(task.notes)}</textarea><p><button type='submit'>Save task</button></p></form><form method='post' action='/agency/projects/{html.escape(project_id, quote=True)}/tasks/{html.escape(task_id, quote=True)}/delete'><button class='danger' type='submit'>Delete task</button></form></section>"""
    return _page("Remediation task", body)


@router.post("/projects/{project_id}/tasks/{task_id}")
async def save_task(project_id: str, task_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_manage_tasks(identity)
    _project(request, identity, project_id)
    current = _task(request, identity, project_id, task_id)
    body = await request.body()
    try:
        replacement = RemediationTask.model_validate(
            current.model_copy(
                update={
                    "status": TaskStatus(_one(body, "status")),
                    "notes": _one(body, "notes"),
                    "owner_label": _one(body, "owner_label"),
                    "due_date": _one(body, "due_date"),
                }
            )
        )
        TenantTaskStore(_root(request)).replace(
            identity,
            TenantTaskStore.ref(identity, task_id),
            replacement,
        )
    except (ValidationError, ValueError, TenantTaskStoreError) as exc:
        raise HTTPException(status_code=400, detail="Task update is invalid.") from exc
    return RedirectResponse(f"/agency/projects/{project_id}/tasks", status_code=303)


@router.post("/projects/{project_id}/tasks/{task_id}/delete")
def delete_task(project_id: str, task_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_manage_tasks(identity)
    _project(request, identity, project_id)
    _task(request, identity, project_id, task_id)
    store = TenantTaskStore(_root(request))
    try:
        store.delete(identity, store.ref(identity, task_id))
    except TenantTaskStoreError as exc:
        raise HTTPException(status_code=404, detail="Remediation task not found.") from exc
    return RedirectResponse(f"/agency/projects/{project_id}/tasks", status_code=303)
