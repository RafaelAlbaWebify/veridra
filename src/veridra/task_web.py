from __future__ import annotations

import html
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .history import HistoryEntry, HistoryError, HistoryStore
from .project_store import ClientProject, ProjectEntry, ProjectStore, ProjectStoreError
from .task_store import RemediationTask, TaskStatus, TaskStore, TaskStoreError

router = APIRouter(tags=["tasks"])


def _tasks() -> TaskStore:
    return TaskStore()


def _projects() -> ProjectStore:
    return ProjectStore()


def _history() -> HistoryStore:
    return HistoryStore()


def _project(project_id: str) -> ClientProject:
    try:
        return _projects().load(project_id)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:1100px;margin:36px auto;padding:0 20px}}section{{background:#fff;border:1px solid #dfe3e8;border-radius:9px;padding:22px;margin-bottom:18px}}label{{display:block;font-weight:700;margin:12px 0 5px}}input,select,textarea{{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}}textarea{{min-height:120px}}button,.button{{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}}.secondary{{background:#5f6873}}.danger{{background:#b42318}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top;overflow-wrap:anywhere}}.muted{{color:#68707a}}.actions{{display:flex;gap:8px;flex-wrap:wrap}}form.inline{{display:inline}}code{{font-size:12px}}@media(max-width:760px){{.row{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}</style></head><body><main>{body}</main></body></html>"""


def _values(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    names = (
        "finding_id",
        "title",
        "status",
        "notes",
        "owner_label",
        "due_date",
        "source_assessment_id",
    )
    return {name: parsed.get(name, [""])[0].strip() for name in names}


def _build(project_id: str, values: dict[str, str]) -> RemediationTask:
    try:
        return RemediationTask(
            project_id=project_id,
            finding_id=values["finding_id"],
            title=values["title"],
            status=TaskStatus(values["status"] or TaskStatus.open.value),
            notes=values["notes"],
            owner_label=values["owner_label"],
            due_date=values["due_date"],
            source_assessment_id=values["source_assessment_id"],
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid remediation task.") from exc


def _options(selected: TaskStatus) -> str:
    return "".join(
        "<option value='{value}'{selected}>{label}</option>".format(
            value=item.value,
            selected=" selected" if item == selected else "",
            label=html.escape(item.value.replace("_", " ").title()),
        )
        for item in TaskStatus
    )


def _form(project_id: str, task: RemediationTask, *, action: str, heading: str) -> str:
    return f"""<section><h1>{html.escape(heading)}</h1><form method='post' action='{html.escape(action, quote=True)}'><input type='hidden' name='finding_id' value='{html.escape(task.finding_id, quote=True)}'><input type='hidden' name='source_assessment_id' value='{task.source_assessment_id}'><div class='row'><div><label for='title'>Task title</label><input id='title' name='title' maxlength='240' required value='{html.escape(task.title, quote=True)}'></div><div><label for='status'>Status</label><select id='status' name='status'>{_options(task.status)}</select></div></div><div class='row'><div><label for='owner_label'>Owner label</label><input id='owner_label' name='owner_label' maxlength='120' value='{html.escape(task.owner_label, quote=True)}'></div><div><label for='due_date'>Due date or target</label><input id='due_date' name='due_date' maxlength='40' value='{html.escape(task.due_date, quote=True)}'></div></div><label for='notes'>Notes</label><textarea id='notes' name='notes' maxlength='5000'>{html.escape(task.notes)}</textarea><p><button type='submit'>Save task</button> <a class='button secondary' href='/projects/{project_id}/tasks'>Cancel</a></p></form></section>"""


def _same_target(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _latest_assessment(project: ClientProject) -> HistoryEntry | None:
    return next(
        (
            entry
            for entry in _history().list()
            if _same_target(entry.target, project.target_url)
        ),
        None,
    )


def _finding_candidates(project_id: str, project: ClientProject) -> str:
    latest = _latest_assessment(project)
    if latest is None:
        return "<p class='muted'>Run and save a project assessment before creating tasks from findings.</p>"
    try:
        assessment = _history().load(latest.id)
    except HistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows = "".join(
        "<tr><td><code>{identifier}</code></td><td>{area}</td><td><strong>{title}</strong></td><td><a class='button' href='/projects/{project}/tasks/new?{query}'>Create task</a></td></tr>".format(
            identifier=html.escape(item.id),
            area=html.escape(item.area),
            title=html.escape(item.title),
            project=project_id,
            query=html.escape(
                urlencode({"assessment": latest.id, "finding": item.id}), quote=True
            ),
        )
        for item in assessment.findings
        if item.status.value == "attention"
    )
    if not rows:
        return "<p class='muted'>The latest saved assessment has no attention findings.</p>"
    return f"""<p class='muted'>Create work directly from attention findings in assessment <a href='/history/{latest.id}'><code>{latest.id}</code></a>.</p><table><thead><tr><th>Finding</th><th>Area</th><th>Title</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table>"""


def _project_rows(entries: list[ProjectEntry]) -> str:
    return "".join(
        "<tr><td><strong>{name}</strong><br><span class='muted'>{client}</span></td><td>{target}</td><td><a class='button' href='/projects/{identifier}/tasks'>Open tasks</a></td></tr>".format(
            name=html.escape(entry.name),
            client=html.escape(entry.client_label or "No client label"),
            target=html.escape(entry.target_url),
            identifier=entry.id,
        )
        for entry in entries
    ) or "<tr><td colspan='3'>Create a client project before managing remediation tasks.</td></tr>"


@router.get("/tasks", response_class=HTMLResponse)
def task_home() -> str:
    body = f"""<section><h1>Remediation tasks</h1><p class='muted'>Choose a saved client project. Task statuses remain explicit operator decisions.</p><p><a class='button secondary' href='/projects'>Manage projects</a> <a class='button secondary' href='/'>Assessment console</a></p></section><section><table><thead><tr><th>Project / client</th><th>Target</th><th>Tasks</th></tr></thead><tbody>{_project_rows(_projects().list())}</tbody></table></section>"""
    return _page("Remediation tasks", body)


@router.get("/projects/{project_id}/tasks", response_class=HTMLResponse)
def task_list(project_id: str, status: str | None = Query(default=None)) -> str:
    project = _project(project_id)
    selected: TaskStatus | None = None
    if status:
        try:
            selected = TaskStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Unknown task status.") from exc
    entries = _tasks().list(project_id=project_id, status=selected)
    rows = "".join(
        "<tr><td><strong>{title}</strong><br><code>{finding}</code></td><td>{status}</td><td>{owner}</td><td>{due}</td><td><div class='actions'><a class='button secondary' href='/projects/{project}/tasks/{identifier}/edit'>Edit</a><a class='button secondary' href='/history/{source}'>Source</a><form class='inline' method='post' action='/projects/{project}/tasks/{identifier}/delete'><button class='danger' type='submit'>Delete</button></form></div></td></tr>".format(
            title=html.escape(task.title),
            finding=html.escape(task.finding_id),
            status=html.escape(task.status.value.replace("_", " ")),
            owner=html.escape(task.owner_label or "Unassigned"),
            due=html.escape(task.due_date or "Not set"),
            project=project_id,
            identifier=identifier,
            source=task.source_assessment_id,
        )
        for identifier, task in entries
    ) or "<tr><td colspan='5'>No remediation tasks match this view.</td></tr>"
    filters = " ".join(
        ["<a class='button secondary' href='?'>All</a>"]
        + [
            f"<a class='button secondary' href='?status={item.value}'>{html.escape(item.value.replace('_', ' ').title())}</a>"
            for item in TaskStatus
        ]
    )
    body = f"""<section><h1>{html.escape(project.name)} remediation tasks</h1><p class='muted'>Statuses are explicit operator decisions; Veridra does not mark work fixed or verified automatically.</p><div class='actions'>{filters}<a class='button' href='/projects/{project_id}/monitor'>Project monitoring</a><a class='button secondary' href='/projects/{project_id}'>Project details</a><a class='button secondary' href='/tasks'>All task projects</a></div></section><section><h2>Tracked work</h2><table><thead><tr><th>Task / finding</th><th>Status</th><th>Owner</th><th>Due</th><th>Actions</th></tr></thead><tbody>{rows}</tbody></table></section><section><h2>Create from latest findings</h2>{_finding_candidates(project_id, project)}</section>"""
    return _page(f"{project.name} tasks", body)


@router.get("/projects/{project_id}/tasks/new", response_class=HTMLResponse)
def new_task(project_id: str, assessment: str, finding: str) -> str:
    _project(project_id)
    try:
        source = _history().load(assessment)
    except HistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    match = next((item for item in source.findings if item.id == finding), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Source finding was not found.")
    task = RemediationTask(
        project_id=project_id,
        finding_id=match.id,
        title=match.title,
        source_assessment_id=assessment,
    )
    return _page(
        "Create remediation task",
        _form(
            project_id,
            task,
            action=f"/projects/{project_id}/tasks",
            heading="Create remediation task",
        ),
    )


@router.post("/projects/{project_id}/tasks")
async def create_task(project_id: str, request: Request) -> RedirectResponse:
    _project(project_id)
    task = _build(project_id, _values(await request.body()))
    try:
        source = _history().load(task.source_assessment_id)
    except HistoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not any(item.id == task.finding_id for item in source.findings):
        raise HTTPException(status_code=400, detail="Source finding was not found.")
    _tasks().save(task)
    return RedirectResponse(f"/projects/{project_id}/tasks", status_code=303)


@router.get("/projects/{project_id}/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task(project_id: str, task_id: str) -> str:
    _project(project_id)
    try:
        task = _tasks().load(task_id)
    except TaskStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Saved remediation task was not found.")
    return _page(
        "Edit remediation task",
        _form(
            project_id,
            task,
            action=f"/projects/{project_id}/tasks/{task_id}/edit",
            heading="Edit remediation task",
        ),
    )


@router.post("/projects/{project_id}/tasks/{task_id}/edit")
async def update_task(project_id: str, task_id: str, request: Request) -> RedirectResponse:
    _project(project_id)
    task = _build(project_id, _values(await request.body()))
    try:
        current = _tasks().load(task_id)
        if current.project_id != project_id:
            raise TaskStoreError("Saved remediation task was not found.")
        _tasks().replace(task_id, task)
    except TaskStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(f"/projects/{project_id}/tasks", status_code=303)


@router.post("/projects/{project_id}/tasks/{task_id}/delete")
def delete_task(project_id: str, task_id: str) -> RedirectResponse:
    _project(project_id)
    try:
        task = _tasks().load(task_id)
        if task.project_id != project_id:
            raise TaskStoreError("Saved remediation task was not found.")
        _tasks().delete(task_id)
    except TaskStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(f"/projects/{project_id}/tasks", status_code=303)
