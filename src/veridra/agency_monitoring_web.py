# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .monitoring_schedule import MonitoringCadence, MonitoringSchedule
from .project_store import ClientProject
from .request_security import require_request_identity
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_monitoring_api import (
    MonitoringConfigurationUpdate,
    replace_monitoring_configuration,
    run_monitoring_assessment,
)
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency", tags=["agency-monitoring"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:920px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}label{display:block;font-weight:700;margin:12px 0 5px}input,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.success{border-left-color:#16794a;background:#f0faf5}.actions{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:700px){.row{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _can_manage(identity: RequestIdentity) -> bool:
    try:
        require_tenant_capability(identity, TenantCapability.manage_monitoring)
    except IdentityBoundaryError:
        return False
    return True


def _project(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
) -> ClientProject:
    store = TenantProjectStore(_root(request))
    try:
        return store.load(identity, store.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


def _option(value: str, selected: str, label: str) -> str:
    marker = " selected" if value == selected else ""
    return f"<option value='{html.escape(value, quote=True)}'{marker}>{html.escape(label)}</option>"


@router.get("/projects/{project_id}/monitoring", response_class=HTMLResponse)
def project_monitoring(
    project_id: str,
    request: Request,
    saved: bool = False,
    assessment_id: str | None = None,
    email_status: str | None = None,
) -> str:
    identity = require_request_identity(request)
    project = _project(request, identity, project_id)
    history = TenantHistoryStore(_root(request))
    try:
        assessments = history.list(identity, project_id)
    except TenantHistoryStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc
    schedule = project.monitoring_schedule
    can_manage = _can_manage(identity)
    cadence_options = "".join(
        _option(item.value, schedule.cadence.value, item.value.title())
        for item in MonitoringCadence
    )
    weekday = "" if schedule.weekday is None else str(schedule.weekday)
    day_of_month = "" if schedule.day_of_month is None else str(schedule.day_of_month)
    recipient = html.escape(str(project.monitoring_email or ""), quote=True)
    status_parts: list[str] = []
    if saved:
        status_parts.append("Monitoring configuration saved.")
    if assessment_id is not None:
        status_parts.append(f"Assessment {html.escape(assessment_id)} saved.")
    if email_status is not None:
        status_parts.append(f"Email status: {html.escape(email_status)}.")
    status_panel = (
        f"<p class='notice success'><strong>{' '.join(status_parts)}</strong></p>"
        if status_parts
        else ""
    )
    latest = assessments[0] if assessments else None
    previous = assessments[1] if len(assessments) > 1 else None
    history_summary = (
        f"<p><strong>Latest assessment:</strong> {html.escape(latest.generated_at) if latest else 'Not available'}<br><strong>Previous assessment:</strong> {html.escape(previous.generated_at) if previous else 'Not available'}</p>"
    )
    if can_manage:
        form = f"""<form method='post' action='/agency/projects/{html.escape(project_id, quote=True)}/monitoring'><div class='row'><div><label for='cadence'>Cadence</label><select id='cadence' name='cadence'>{cadence_options}</select></div><div><label for='timezone'>Timezone</label><input id='timezone' name='timezone' maxlength='64' value='{html.escape(schedule.timezone, quote=True)}' required></div></div><div class='row'><div><label for='hour'>Hour</label><input id='hour' name='hour' type='number' min='0' max='23' value='{schedule.hour}' required></div><div><label for='minute'>Minute</label><input id='minute' name='minute' type='number' min='0' max='59' value='{schedule.minute}' required></div></div><div class='row'><div><label for='weekday'>Weekday (0 Monday–6 Sunday)</label><input id='weekday' name='weekday' type='number' min='0' max='6' value='{html.escape(weekday, quote=True)}'></div><div><label for='day_of_month'>Day of month (1–28)</label><input id='day_of_month' name='day_of_month' type='number' min='1' max='28' value='{html.escape(day_of_month, quote=True)}'></div></div><label for='recipient'>Notification email</label><input id='recipient' name='recipient' type='email' value='{recipient}'><p class='muted'>Saving this form explicitly replaces the project monitoring configuration. It does not run an assessment.</p><button type='submit'>Save monitoring configuration</button></form>"""
        run_action = f"<form method='post' action='/agency/projects/{html.escape(project_id, quote=True)}/monitoring/run'><button type='submit'>Run monitoring now</button></form>"
    else:
        form = "<p class='notice'>Your current workspace role can inspect this configuration but cannot change it.</p>"
        run_action = ""
    body = f"""<section><p><a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project</a> · <a href='/agency'>Agency workflow</a></p><h1>Monitoring for {html.escape(project.name)}</h1>{status_panel}<p><strong>Website:</strong> {html.escape(project.target_url)}<br><strong>Current cadence:</strong> {html.escape(schedule.cadence.value)}<br><strong>Timezone:</strong> {html.escape(schedule.timezone)}<br><strong>Notification:</strong> {html.escape(str(project.monitoring_email or 'Not configured'))}</p>{history_summary}</section><section><h2>Configuration</h2>{form}</section><section><h2>Manual verification</h2><p class='muted'>A manual run performs the existing bounded assessment, saves it to this tenant project and attempts the configured summary email. Email delivery status is evidence of the attempt, not a guarantee of receipt.</p>{run_action}</section>"""
    return _page(f"{project.name} monitoring", body)


@router.post("/projects/{project_id}/monitoring")
async def save_project_monitoring(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_monitoring)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    body = await request.body()
    try:
        schedule = MonitoringSchedule(
            cadence=MonitoringCadence(_single(body, "cadence")),
            timezone=_single(body, "timezone"),
            hour=int(_single(body, "hour")),
            minute=int(_single(body, "minute")),
            weekday=int(_single(body, "weekday")) if _single(body, "weekday") else None,
            day_of_month=(
                int(_single(body, "day_of_month"))
                if _single(body, "day_of_month")
                else None
            ),
        )
        payload = MonitoringConfigurationUpdate(
            schedule=schedule,
            recipient=_single(body, "recipient") or None,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Monitoring configuration is invalid.") from exc
    replace_monitoring_configuration(project_id, payload, request, identity)
    return RedirectResponse(
        f"/agency/projects/{project_id}/monitoring?{urlencode({'saved': 'true'})}",
        status_code=303,
    )


@router.post("/projects/{project_id}/monitoring/run")
def run_project_monitoring(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_monitoring)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    result = run_monitoring_assessment(project_id, request, identity)
    query: dict[str, str] = {"assessment_id": result.assessment_id}
    if result.email_status is not None:
        query["email_status"] = result.email_status.value
    return RedirectResponse(
        f"/agency/projects/{project_id}/monitoring?{urlencode(query)}",
        status_code=303,
    )
