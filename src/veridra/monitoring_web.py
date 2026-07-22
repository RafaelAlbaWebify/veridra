from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .collector import CollectionError
from .core import UnsafeTargetError
from .history import HistoryStore
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


@router.get("", response_class=HTMLResponse)
def monitoring_dashboard(
    succeeded: int | None = Query(default=None, ge=0),
    failed: int | None = Query(default=None, ge=0),
    truncated: bool = False,
) -> str:
    rows = "".join(
        "<tr><td><strong>{name}</strong><br>{target}</td><td>{cadence}</td>"
        "<td>{status}</td><td>{last}</td><td>{due}</td><td><div class='actions'>"
        "<form method='post' action='/monitoring/projects/{identifier}/run'>"
        "<button>Run now</button></form>"
        "<a class='button' href='/monitoring/projects/{identifier}/schedule'>Schedule</a>"
        "<a class='button' href='/projects/{identifier}/monitor'>History</a>"
        "</div></td></tr>".format(
            name=html.escape(item.project_name),
            target=html.escape(item.target_url),
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
        "No background service or automatic delivery is installed.</p>"
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
    HistoryStore().save(assessment)
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
    )
    body = (
        f"<section><h1>Monitoring schedule — {html.escape(project.name)}</h1>"
        "<p class='muted'>Runs occur only when triggered while Veridra is running.</p>"
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
        replacement = project.model_copy(update={"monitoring_schedule": schedule})
        new_id = ProjectStore().replace(entry_id, replacement)
    except (ValidationError, ValueError, ProjectStoreError) as exc:
        raise HTTPException(status_code=400, detail="Invalid monitoring schedule.") from exc
    return RedirectResponse(f"/monitoring/projects/{new_id}/schedule", status_code=303)
