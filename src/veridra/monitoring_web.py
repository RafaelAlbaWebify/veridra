# ruff: noqa: E501
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


def _page(body: str, *, title: str = "Monitoring operations") -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:1200px;margin:36px auto;padding:0 20px}}section{{background:white;border:1px solid #dfe3e8;border-radius:9px;padding:22px;margin-bottom:18px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}}button,.button{{display:inline-block;border:0;border-radius:7px;background:#22272d;color:white;padding:10px 14px;text-decoration:none;cursor:pointer}}.secondary{{background:#5f6873}}.muted{{color:#68707a}}.pill{{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid}}.due{{color:#8a5c00;background:#fff8e5}}.overdue{{color:#a32418;background:#fff0ee}}.upcoming{{color:#1769aa;background:#eef6fc}}.manual{{color:#59636e;background:#f1f3f5}}.actions{{display:flex;gap:8px;flex-wrap:wrap}}label{{display:block;font-weight:700;margin:12px 0 5px}}input,select{{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}@media(max-width:760px){{table{{display:block;overflow:auto}}.grid{{grid-template-columns:1fr}}}}</style></head><body><main>{body}</main></body></html>"""


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
    states = project_monitoring_states()
    rows = "".join(
        "<tr><td><strong>{name}</strong><br><span class='muted'>{target}</span></td>"
        "<td>{cadence}</td><td><span class='pill {status}'>{status}</span></td>"
        "<td>{last}</td><td>{next_due}</td><td><div class='actions'>"
        "<form method='post' action='/monitoring/projects/{identifier}/run'>"
        "<button type='submit'>Run now</button></form>"
        "<a class='button secondary' href='/monitoring/projects/{identifier}/schedule'>Schedule</a>"
        "<a class='button secondary' href='/projects/{identifier}/monitor'>History</a>"
        "</div></td></tr>".format(
            name=html.escape(item.project_name),
            target=html.escape(item.target_url),
            cadence=html.escape(item.cadence.title()),
            status=html.escape(item.status),
            last=_format_time(item.last_run),
            next_due=_format_time(item.next_due),
            identifier=item.project_id,
        )
        for item in states
    ) or "<tr><td colspan='6'>No saved projects are available.</td></tr>"
    outcome = ""
    if succeeded is not None or failed is not None:
        outcome = (
            "<section><strong>Batch completed.</strong> "
            f"Succeeded: {succeeded or 0}. Failed: {failed or 0}."
            + (" The batch limit was reached." if truncated else "")
            + "</section>"
        )
    body = (
        "<section><h1>Monitoring operations</h1>"
        "<p class='muted'>Schedules are evaluated only while Veridra is running. "
        "This page does not install a background service or claim automatic delivery.</p>"
        "<div class='actions'><form method='post' action='/monitoring/run-due'>"
        "<button type='submit'>Run due projects</button></form>"
        "<a class='button secondary' href='/projects'>Client projects</a></div></section>"
        + outcome
        + "<section><table><thead><tr><th>Project</th><th>Cadence</th><th>Status</th>"
        "<th>Last run</th><th>Next due</th><th>Actions</th></tr></thead><tbody>"
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
    return _page(
        f"""<section><h1>Monitoring schedule — {html.escape(project.name)}</h1>
<p class='muted'>Schedules are local configuration. Runs occur only when triggered while Veridra is running.</p>
<form method='post' action='/monitoring/projects/{entry_id}/schedule'>
<div class='grid'><div><label for='cadence'>Cadence</label><select id='cadence' name='cadence'>{options}</select></div>
<div><label for='timezone'>IANA timezone</label><input id='timezone' name='timezone' maxlength='64' value='{html.escape(schedule.timezone, quote=True)}' required></div>
<div><label for='hour'>Hour (0–23)</label><input id='hour' name='hour' type='number' min='0' max='23' value='{schedule.hour}' required></div>
<div><label for='minute'>Minute (0–59)</label><input id='minute' name='minute' type='number' min='0' max='59' value='{schedule.minute}' required></div>
<div><label for='weekday'>Weekday for weekly runs (0 Monday–6 Sunday)</label><input id='weekday' name='weekday' type='number' min='0' max='6' value='{schedule.weekday if schedule.weekday is not None else ''}'></div>
<div><label for='day_of_month'>Day for monthly runs (1–28)</label><input id='day_of_month' name='day_of_month' type='number' min='1' max='28' value='{schedule.day_of_month if schedule.day_of_month is not None else ''}'></div></div>
<p><button type='submit'>Save schedule</button> <a class='button secondary' href='/monitoring'>Cancel</a></p></form></section>""",
        title=f"Schedule {project.name}",
    )


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
        schedule = MonitoringSchedule.model_validate(
            {
                "cadence": value("cadence") or "manual",
                "timezone": value("timezone") or "UTC",
                "hour": int(value("hour") or "9"),
                "minute": int(value("minute") or "0"),
                "weekday": int(value("weekday")) if value("weekday") is not None else None,
                "day_of_month": (
                    int(value("day_of_month"))
                    if value("day_of_month") is not None
                    else None
                ),
            }
        )
        replacement = project.model_copy(update={"monitoring_schedule": schedule})
        new_id = ProjectStore().replace(entry_id, replacement)
    except (ValidationError, ValueError, ProjectStoreError) as exc:
        raise HTTPException(status_code=400, detail="Invalid monitoring schedule.") from exc
    return RedirectResponse(f"/monitoring/projects/{new_id}/schedule", status_code=303)
