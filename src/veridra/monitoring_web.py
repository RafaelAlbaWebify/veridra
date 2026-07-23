# ruff: noqa: E501, UP032
from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .collector import CollectionError
from .core import UnsafeTargetError
from .email_delivery import (
    EmailAttemptStore,
    EmailDeliveryError,
    send_monitoring_summary,
)
from .history import HistoryError, HistoryStore
from .monitoring_ops import project_monitoring_states, run_due_projects
from .monitoring_schedule import MonitoringSchedule
from .project_store import ClientProject, ProjectStore, ProjectStoreError
from .service import assess_url

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

_STYLE = """
body{font:14px Arial;margin:0;background:#f7f8fa;color:#17191c}
main{max-width:1200px;margin:36px auto;padding:0 20px}
section{background:#fff;border:1px solid #dfe3e8;padding:22px;margin-bottom:18px}
table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #ddd}
button,.button{display:inline-block;background:#22272d;color:#fff;padding:9px 12px;border:0;text-decoration:none}
.actions{display:flex;gap:8px;flex-wrap:wrap}.muted{color:#68707a}
label{display:block;font-weight:700;margin-top:10px}input,select{width:100%;padding:9px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:760px){table{display:block;overflow:auto}.grid{grid-template-columns:1fr}}
"""


def _page(body: str, *, title: str = "Monitoring operations") -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


def _format_time(value: datetime | None) -> str:
    return html.escape(value.isoformat()) if value is not None else "Not available"


def _load_project(entry_id: str) -> ClientProject:
    try:
        return ProjectStore().load(entry_id)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _send_project_email(
    project_id: str,
    project: ClientProject,
    assessment_id: str,
) -> None:
    if project.monitoring_email is None:
        return
    assessment = HistoryStore().load(assessment_id)
    send_monitoring_summary(
        project_id=project_id,
        project_name=project.name,
        target_url=project.target_url,
        assessment_id=assessment_id,
        assessment=assessment,
        recipient=str(project.monitoring_email),
    )


def _email_rows(project_id: str) -> str:
    rows = "".join(
        "<tr><td>{number}</td><td>{status}</td><td>{recipient}</td><td>{time}</td><td>{error}</td></tr>".format(
            number=attempt.attempt_number,
            status=html.escape(attempt.status.value),
            recipient=html.escape(str(attempt.recipient)),
            time=html.escape(attempt.attempted_at.isoformat()),
            error=html.escape(attempt.error or "—"),
        )
        for _, attempt in EmailAttemptStore().list_for_related(project_id)
    )
    return rows or "<tr><td colspan='5'>No monitoring email has been attempted.</td></tr>"


@router.get("", response_class=HTMLResponse)
def monitoring_dashboard(
    succeeded: int | None = Query(default=None, ge=0),
    failed: int | None = Query(default=None, ge=0),
    truncated: bool = False,
) -> str:
    rows = "".join(
        "<tr><td><strong>{name}</strong><br>{target}<br><span class='muted'>{email}</span></td><td>{cadence}</td>"
        "<td>{status}</td><td>{last}</td><td>{due}</td><td><div class='actions'>"
        "<form method='post' action='/monitoring/projects/{identifier}/run'>"
        "<button>Run now</button></form>"
        "<a class='button' href='/monitoring/projects/{identifier}/schedule'>Schedule & email</a>"
        "<a class='button' href='/monitoring/projects/{identifier}/email'>Email history</a>"
        "<a class='button' href='/projects/{identifier}/monitor'>History</a>"
        "</div></td></tr>".format(
            name=html.escape(item.project_name),
            target=html.escape(item.target_url),
            email=html.escape(str(_load_project(item.project_id).monitoring_email or "No email recipient")),
            cadence=html.escape(item.cadence.title()),
            status=html.escape(item.status),
            last=_format_time(item.last_run),
            due=_format_time(item.next_due),
            identifier=item.project_id,
        )
        for item in project_monitoring_states()
    ) or "<tr><td colspan='6'>No saved projects are available.</td></tr>"
    outcome = ""
    if succeeded is not None or failed is not None:
        suffix = " The batch limit was reached." if truncated else ""
        outcome = (
            "<section><strong>Batch completed.</strong> "
            f"Succeeded: {succeeded or 0}. Failed: {failed or 0}.{suffix}</section>"
        )
    body = (
        "<section><h1>Monitoring operations</h1>"
        "<p class='muted'>Schedules are evaluated only while Veridra is running. "
        "SMTP summaries are sent only after successful explicit runs; no background service or automatic retry scheduler is installed.</p>"
        "<div class='actions'><form method='post' action='/monitoring/run-due'>"
        "<button>Run due projects</button></form>"
        "<a class='button' href='/projects'>Client projects</a></div></section>"
        + outcome
        + "<section><table><thead><tr><th>Project</th><th>Cadence</th>"
        "<th>Status</th><th>Last run</th><th>Next due</th><th>Actions</th>"
        "</tr></thead><tbody>"
        + rows
        + "</tbody></table></section>"
    )
    return _page(body)


@router.post("/run-due")
def run_due_batch() -> RedirectResponse:
    outcome = run_due_projects()
    for item in outcome.items:
        if not item.succeeded or item.assessment_id is None:
            continue
        try:
            project = ProjectStore().load(item.project_id)
            _send_project_email(item.project_id, project, item.assessment_id)
        except (ProjectStoreError, HistoryError, EmailDeliveryError):
            continue
    query = urlencode(
        {
            "succeeded": outcome.succeeded,
            "failed": outcome.failed,
            "truncated": str(outcome.truncated).lower(),
        }
    )
    return RedirectResponse(f"/monitoring?{query}", status_code=303)


@router.post("/projects/{entry_id}/run")
def run_project_now(entry_id: str) -> RedirectResponse:
    project = _load_project(entry_id)
    try:
        assessment = assess_url(
            project.target_url,
            crawl_profile=project.resolved_crawl_profile(),
        )
    except (UnsafeTargetError, CollectionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assessment_id = HistoryStore().save(assessment)
    try:
        _send_project_email(entry_id, project, assessment_id)
    except (HistoryError, EmailDeliveryError):
        pass
    return RedirectResponse(f"/projects/{entry_id}/monitor", status_code=303)


def _schedule_form(entry_id: str, project: ClientProject) -> str:
    schedule = project.monitoring_schedule
    options = "".join(
        f"<option value='{value}'{' selected' if schedule.cadence.value == value else ''}>"
        f"{value.title()}</option>"
        for value in ("manual", "daily", "weekly", "monthly")
    )
    fields = (
        f"<label>Cadence</label><select name='cadence'>{options}</select>"
        f"<label>Timezone</label><input name='timezone' value='{html.escape(schedule.timezone)}'>"
        f"<label>Hour</label><input name='hour' type='number' value='{schedule.hour}'>"
        f"<label>Minute</label><input name='minute' type='number' value='{schedule.minute}'>"
        f"<label>Weekday</label><input name='weekday' type='number' value='{schedule.weekday or ''}'>"
        "<label>Day of month</label><input name='day_of_month' type='number' "
        f"value='{schedule.day_of_month or ''}'>"
        "<label>Monitoring email</label><input name='monitoring_email' type='email' maxlength='320' "
        f"value='{html.escape(str(project.monitoring_email or ''), quote=True)}'>"
    )
    body = (
        f"<section><h1>Monitoring schedule — {html.escape(project.name)}</h1>"
        "<p class='muted'>Runs occur only when triggered while Veridra is running. SMTP credentials are read from VERIDRA_SMTP_* environment variables and are not stored with the project.</p>"
        f"<form method='post' action='/monitoring/projects/{entry_id}/schedule'>"
        f"<div class='grid'>{fields}</div><p><button>Save schedule</button></p></form>"
        "</section>"
    )
    return _page(body, title=f"Schedule {project.name}")


@router.get("/projects/{entry_id}/schedule", response_class=HTMLResponse)
def edit_schedule(entry_id: str) -> str:
    return _schedule_form(entry_id, _load_project(entry_id))


@router.post("/projects/{entry_id}/schedule")
async def save_schedule(entry_id: str, request: Request) -> RedirectResponse:
    project = _load_project(entry_id)
    parsed = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)

    def value(name: str) -> str | None:
        raw = parsed.get(name, [""])[0].strip()
        return raw or None

    try:
        weekday = value("weekday")
        day_of_month = value("day_of_month")
        schedule = MonitoringSchedule.model_validate(
            {
                "cadence": value("cadence") or "manual",
                "timezone": value("timezone") or "UTC",
                "hour": int(value("hour") or "9"),
                "minute": int(value("minute") or "0"),
                "weekday": int(weekday) if weekday is not None else None,
                "day_of_month": (
                    int(day_of_month) if day_of_month is not None else None
                ),
            }
        )
        replacement = ClientProject.model_validate(
            project.model_copy(
                update={
                    "monitoring_schedule": schedule,
                    "monitoring_email": value("monitoring_email"),
                }
            )
        )
        new_id = ProjectStore().replace(entry_id, replacement)
    except (ValidationError, ValueError, ProjectStoreError) as exc:
        raise HTTPException(status_code=400, detail="Invalid monitoring schedule or email.") from exc
    return RedirectResponse(f"/monitoring/projects/{new_id}/schedule", status_code=303)


@router.get("/projects/{entry_id}/email", response_class=HTMLResponse)
def project_email_history(entry_id: str) -> str:
    project = _load_project(entry_id)
    retry = (
        f"<form method='post' action='/monitoring/projects/{entry_id}/email/retry'><button>Retry latest summary</button></form>"
        if project.monitoring_email
        else "<p class='muted'>No monitoring email recipient is configured.</p>"
    )
    body = f"""<section><h1>Email delivery — {html.escape(project.name)}</h1><p><strong>Recipient:</strong> {html.escape(str(project.monitoring_email or 'Disabled'))}</p>{retry}<p><a class='button' href='/monitoring'>Back to monitoring</a></p></section><section><table><thead><tr><th>Attempt</th><th>Status</th><th>Recipient</th><th>Time</th><th>Error</th></tr></thead><tbody>{_email_rows(entry_id)}</tbody></table></section>"""
    return _page(body, title=f"Email delivery {project.name}")


@router.post("/projects/{entry_id}/email/retry")
def retry_project_email(entry_id: str) -> RedirectResponse:
    project = _load_project(entry_id)
    if project.monitoring_email is None:
        raise HTTPException(status_code=400, detail="Monitoring email is not configured.")
    entries = [
        item
        for item in HistoryStore().list()
        if item.target.rstrip("/") == project.target_url.rstrip("/")
    ]
    if not entries:
        raise HTTPException(status_code=400, detail="No saved project assessment is available.")
    try:
        _send_project_email(entry_id, project, entries[0].id)
    except (HistoryError, EmailDeliveryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/monitoring/projects/{entry_id}/email", status_code=303)
