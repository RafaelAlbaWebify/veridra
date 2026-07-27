# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .core import Assessment
from .finding_task_api import FindingTaskConversion, create_task_from_finding
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .project_store import ClientProject
from .request_security import require_request_identity
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .tenant_task_store import TenantTaskStore

router = APIRouter(prefix="/agency", tags=["agency-remediation"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1080px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}table{width:100%;border-collapse:collapse}th,td{padding:12px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top;overflow-wrap:anywhere}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.pill{display:inline-block;border:1px solid #cfd4da;border-radius:999px;padding:3px 8px}.actions{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:760px){table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _load_source(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
    assessment_id: str,
) -> tuple[ClientProject, Assessment]:
    projects = TenantProjectStore(_root(request))
    history = TenantHistoryStore(_root(request))
    try:
        project = projects.load(identity, projects.ref(identity, project_id))
        assessment = history.load(
            identity,
            history.ref(identity, project_id, assessment_id),
        )
    except (TenantProjectStoreError, TenantHistoryStoreError) as exc:
        raise HTTPException(status_code=404, detail="Finding source not found.") from exc
    return project, assessment


def _can_manage_tasks(identity: RequestIdentity) -> bool:
    try:
        require_tenant_capability(identity, TenantCapability.manage_tasks)
    except IdentityBoundaryError:
        return False
    return True


@router.get(
    "/projects/{project_id}/assessments/{assessment_id}/findings",
    response_class=HTMLResponse,
)
def saved_findings(
    project_id: str,
    assessment_id: str,
    request: Request,
) -> str:
    identity = require_request_identity(request)
    project, assessment = _load_source(request, identity, project_id, assessment_id)
    tasks = TenantTaskStore(_root(request)).list(identity, project_id=project_id)
    task_keys = {(task.source_assessment_id, task.finding_id): task_id for task_id, task in tasks}
    can_create = _can_manage_tasks(identity)
    rows: list[str] = []
    for finding in assessment.findings:
        key = (assessment_id, finding.id)
        existing = task_keys.get(key)
        if existing is not None:
            action = f"<span class='pill'>Task {html.escape(existing)}</span>"
        elif can_create:
            query = html.escape(
                urlencode(
                    {
                        "project_id": project_id,
                        "assessment_id": assessment_id,
                        "finding_id": finding.id,
                    }
                ),
                quote=True,
            )
            action = f"<a class='button' href='/agency/tasks/from-finding?{query}'>Create task</a>"
        else:
            action = "<span class='muted'>Task permission required</span>"
        rows.append(
            f"<tr><td><span class='pill'>{html.escape(finding.status.value)}</span></td><td>{html.escape(finding.area)}</td><td><strong>{html.escape(finding.title)}</strong><br><span class='muted'>{html.escape(finding.summary)}</span></td><td>{action}</td></tr>"
        )
    body = f"""<section><p><a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project</a> · <a href='/agency'>Agency workflow</a></p><h1>Saved findings for {html.escape(project.name)}</h1><p class='notice'>Tasks are created one finding at a time after explicit confirmation. Creating a task records remediation work; it does not prove the finding is fixed.</p><table><thead><tr><th>Status</th><th>Area</th><th>Finding</th><th>Remediation</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>"""
    return _page(f"{project.name} findings", body)


@router.get("/tasks/from-finding", response_class=HTMLResponse)
def confirm_finding_task(
    project_id: str,
    assessment_id: str,
    finding_id: str,
    request: Request,
) -> str:
    identity = require_request_identity(request)
    if not _can_manage_tasks(identity):
        raise HTTPException(status_code=403, detail="This action is not permitted.")
    project, assessment = _load_source(request, identity, project_id, assessment_id)
    finding = next((item for item in assessment.findings if item.id == finding_id), None)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding source not found.")
    hidden = "".join(
        (
            f"<input type='hidden' name='project_id' value='{html.escape(project_id, quote=True)}'>",
            f"<input type='hidden' name='assessment_id' value='{html.escape(assessment_id, quote=True)}'>",
            f"<input type='hidden' name='finding_id' value='{html.escape(finding_id, quote=True)}'>",
        )
    )
    recommendation = finding.recommendation or "Review the supporting evidence."
    body = f"""<section><p><a href='/agency/projects/{html.escape(project_id, quote=True)}/assessments/{html.escape(assessment_id, quote=True)}/findings'>Saved findings</a></p><h1>Create remediation task</h1><p class='notice'><strong>Project:</strong> {html.escape(project.name)}<br><strong>Finding:</strong> {html.escape(finding.title)}</p><p><strong>Area:</strong> {html.escape(finding.area)}<br><strong>Severity:</strong> {html.escape(finding.severity)}<br><strong>Observation:</strong> {html.escape(finding.summary)}<br><strong>Recommended fix:</strong> {html.escape(recommendation)}</p><form method='post' action='/agency/tasks/from-finding'>{hidden}<button type='submit'>Confirm task creation</button> <a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/assessments/{html.escape(assessment_id, quote=True)}/findings'>Cancel</a></form></section>"""
    return _page("Create remediation task", body)


@router.post("/tasks/from-finding")
async def submit_finding_task(request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_tasks)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    body = await request.body()
    payload = FindingTaskConversion(
        project_id=_single(body, "project_id"),
        assessment_id=_single(body, "assessment_id"),
        finding_id=_single(body, "finding_id"),
    )
    created = create_task_from_finding(payload, request, identity)
    query = urlencode({"task_created": created.task_id})
    return RedirectResponse(f"/agency/projects/{payload.project_id}?{query}", status_code=303)
