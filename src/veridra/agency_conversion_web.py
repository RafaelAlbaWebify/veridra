# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .app import dashboard
from .assessment_project_conversion_api import AssessmentProjectConversion, convert_assessment
from .collector import CollectionError
from .core import UnsafeTargetError, demo_assessment
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .request_security import require_request_identity
from .service import assess_url
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_profile_store import TenantProfileStore
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency", tags=["agency-conversion"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:920px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;font-weight:700;margin:12px 0 5px}input,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.success{border-left-color:#16794a;background:#f0faf5}.actions{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:700px){.row{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _identity(request: Request) -> RequestIdentity | None:
    try:
        return require_request_identity(request)
    except HTTPException:
        return None


def _can_manage_projects(identity: RequestIdentity) -> bool:
    try:
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError:
        return False
    return True


def _profile_options(request: Request, identity: RequestIdentity, selected: str | None) -> str:
    entries = TenantProfileStore(_root(request)).list(identity)
    options = ["<option value=''>Default Veridra report</option>"]
    options.extend(
        "<option value='{identifier}'{selected}>{label}</option>".format(
            identifier=html.escape(entry.id, quote=True),
            selected=" selected" if entry.id == selected else "",
            label=html.escape(f"{entry.organisation_name} — {entry.client_name}" if entry.client_name else entry.organisation_name),
        )
        for entry in entries
    )
    return "".join(options)


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


@router.get("/audit", response_class=HTMLResponse)
def completed_agency_audit(url: str) -> str:
    try:
        assessment = assess_url(url)
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized = str(assessment.target)
    conversion_query = html.escape(urlencode({"url": normalized}), quote=True)
    action = f"<section><h3>Continue with this audit</h3><p class='muted'>This assessment is still temporary. Create a tenant-qualified client project only after explicit confirmation.</p><a class='button' href='/agency/convert?{conversion_query}'>Create client project</a> <a class='button secondary' href='/agency'>Back to agency workflow</a></section>"
    rendered = dashboard(
        assessment,
        submitted_url=normalized,
        profile_entries=[],
    )
    return rendered.replace("<div class='cards'>", action + "<div class='cards'>", 1)


@router.get("/convert", response_class=HTMLResponse)
def conversion_confirmation(request: Request, url: str, profile: str | None = None, demo: bool = False) -> str:
    identity = _identity(request)
    if identity is None:
        return _page(
            "Sign in required",
            "<section><h1>Sign in to create a client project</h1><p>This completed quick audit remains temporary. Sign in before creating tenant-qualified client work.</p><p><a class='button' href='/login'>Sign in</a> <a class='button secondary' href='/agency'>Back to agency workflow</a></p></section>",
        )
    if not _can_manage_projects(identity):
        return _page(
            "Project permission required",
            "<section><h1>Project creation is not permitted</h1><p>Your current workspace role can review this audit but cannot create client projects.</p><p><a class='button secondary' href='/agency'>Back to agency workflow</a></p></section>",
        )
    target = "Demo assessment" if demo else url
    options = _profile_options(request, identity, profile)
    hidden = "<input type='hidden' name='demo' value='true'>" if demo else f"<input type='hidden' name='url' value='{html.escape(url, quote=True)}'>"
    body = f"""<section><p><a href='/agency'>Agency workflow</a> · <a href='/'>Assessment</a></p><h1>Create client project</h1><p class='notice'><strong>Audited target:</strong> {html.escape(target)}<br>This confirmation revalidates the same public target before tenant persistence. No project is created by opening this page.</p><form method='post' action='/agency/convert'>{hidden}<div class='row'><div><label for='project_name'>Project name</label><input id='project_name' name='project_name' maxlength='120' required></div><div><label for='client_label'>Client label</label><input id='client_label' name='client_label' maxlength='120'></div></div><label for='profile_id'>Tenant report profile</label><select id='profile_id' name='profile_id'>{options}</select><p class='muted'>Only report profiles belonging to the authenticated workspace are available.</p><p><button type='submit'>Create client project</button> <a class='button secondary' href='/'>Cancel</a></p></form></section>"""
    return _page("Create client project", body)


@router.post("/convert")
async def submit_conversion(request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    body = await request.body()
    url = _single(body, "url")
    demo = _single(body, "demo") == "true"
    try:
        assessment = demo_assessment() if demo else assess_url(url)
        payload = AssessmentProjectConversion(
            assessment=assessment,
            project_name=_single(body, "project_name"),
            client_label=_single(body, "client_label") or None,
            profile_id=_single(body, "profile_id") or None,
        )
    except (UnsafeTargetError, CollectionError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Project conversion input is invalid.") from exc
    created = convert_assessment(payload, request, identity)
    return RedirectResponse(f"/agency/projects/{created.project_id}", status_code=303)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def tenant_project_next_actions(
    project_id: str,
    request: Request,
    task_created: str | None = None,
) -> str:
    identity = require_request_identity(request)
    projects = TenantProjectStore(_root(request))
    history = TenantHistoryStore(_root(request))
    try:
        project = projects.load(identity, projects.ref(identity, project_id))
        assessments = history.list(identity, project_id)
    except (TenantProjectStoreError, TenantHistoryStoreError) as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc
    query = urlencode({"url": project.target_url, **({"profile": project.profile_id} if project.profile_id else {})})
    latest = assessments[0] if assessments else None
    latest_text = html.escape(latest.generated_at) if latest else "Not available"
    remediation = (
        f"<a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/assessments/{html.escape(latest.id, quote=True)}/findings'>Create remediation tasks</a>"
        if latest is not None
        else "<span class='muted'>Save an assessment before creating remediation tasks.</span>"
    )
    created_notice = (
        f"<p class='notice success'><strong>Remediation task created:</strong> {html.escape(task_created)}</p>"
        if task_created
        else ""
    )
    body = f"""<section><p><a href='/agency'>Agency workflow</a></p><h1>{html.escape(project.name)}</h1>{created_notice}<p><strong>Client:</strong> {html.escape(project.client_label or 'Not set')}<br><strong>Website:</strong> {html.escape(project.target_url)}<br><strong>Saved assessment:</strong> {latest_text}</p><div class='actions'><a class='button' href='/?{html.escape(query, quote=True)}'>Review assessment</a><a class='button secondary' href='/report?{html.escape(query, quote=True)}'>Configure report</a>{remediation}<a class='button secondary' href='/monitoring'>Enable monitoring</a></div></section><section><h2>Recommended next step</h2><p>Review the saved evidence, choose the client-facing report output, then convert actionable findings into assigned remediation work before enabling recurring monitoring.</p></section>"""
    return _page(project.name, body)
