from __future__ import annotations

import html
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from .collector import CollectionError
from .core import UnsafeTargetError
from .history import Comparison, HistoryEntry, HistoryError, HistoryStore
from .project_store import ClientProject, ProjectStore, ProjectStoreError
from .service import assess_url

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _same_target(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _project(entry_id: str) -> ClientProject:
    try:
        return ProjectStore().load(entry_id)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _entries(project: ClientProject) -> list[HistoryEntry]:
    return [
        entry
        for entry in HistoryStore().list()
        if _same_target(entry.target, project.target_url)
    ]


def _comparison(entries: list[HistoryEntry]) -> Comparison | None:
    if len(entries) < 2:
        return None
    try:
        return HistoryStore().compare(entries[1].id, entries[0].id)
    except HistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _page(body: str, *, title: str) -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:1100px;margin:36px auto;padding:0 20px}}section{{background:white;border:1px solid #dfe3e8;border-radius:9px;padding:22px;margin-bottom:18px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.card{{background:#fff;border:1px solid #dfe3e8;border-radius:9px;padding:18px}}.card strong{{display:block;font-size:26px;margin-top:8px}}.muted{{color:#68707a}}button,.button{{display:inline-block;border:0;border-radius:7px;background:#22272d;color:white;padding:10px 15px;text-decoration:none;cursor:pointer}}.secondary{{background:#5f6873}}.actions{{display:flex;gap:8px;flex-wrap:wrap}}code{{overflow-wrap:anywhere}}@media(max-width:760px){{.cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}table{{display:block;overflow:auto}}}}</style></head><body><main>{body}</main></body></html>"""


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
def monitoring_index() -> str:
    projects = ProjectStore().list()
    rows = "".join(
        "<tr><td><strong>{name}</strong><br><span class='muted'>{client}</span></td><td>{target}</td><td><a class='button' href='/monitoring/{identifier}'>Open monitoring</a></td></tr>".format(
            name=html.escape(item.name),
            client=html.escape(item.client_label or "No client label"),
            target=html.escape(item.target_url),
            identifier=item.id,
        )
        for item in projects
    ) or "<tr><td colspan='3'>No client projects are available.</td></tr>"
    return _page(
        "<section><h1>Project monitoring</h1><p class='muted'>Operator-triggered reassessment and local change evidence.</p><p><a class='button secondary' href='/projects'>Manage projects</a></p></section><section><table><thead><tr><th>Project</th><th>Target</th><th>Action</th></tr></thead><tbody>" + rows + "</tbody></table></section>",
        title="Project monitoring",
    )


@router.post("/{entry_id}/run")
def run_project_assessment(entry_id: str) -> RedirectResponse:
    project = _project(entry_id)
    try:
        assessment = assess_url(project.target_url)
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    HistoryStore().save(assessment)
    return RedirectResponse(f"/monitoring/{entry_id}", status_code=303)


@router.get("/{entry_id}", response_class=HTMLResponse)
def project_monitoring(entry_id: str) -> str:
    project = _project(entry_id)
    entries = _entries(project)
    comparison = _comparison(entries)
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
        compare_query = html.escape(
            urlencode({"before": comparison.before_id, "after": comparison.after_id}),
            quote=True,
        )
        compare_link = f"<a class='button secondary' href='/history/compare?{compare_query}'>Open full comparison</a>"
    latest_text = html.escape(latest.generated_at) if latest else "Not yet assessed"
    previous_text = html.escape(previous.generated_at) if previous else "Not available"
    body = f"""<section><h1>{html.escape(project.name)}</h1><p><strong>Client:</strong> {html.escape(project.client_label or 'Not set')}<br><strong>Website:</strong> {html.escape(project.target_url)}<br><strong>Latest run:</strong> {latest_text}<br><strong>Previous run:</strong> {previous_text}</p><div class='actions'><form method='post' action='/monitoring/{entry_id}/run'><button type='submit'>Run and save assessment</button></form>{compare_link}<a class='button secondary' href='/projects/{entry_id}'>Project details</a><a class='button secondary' href='/monitoring'>All monitored projects</a></div></section><section><p class='muted'>{html.escape(comparison_note)}</p><div class='cards'>{metrics}</div></section><section><h2>Project run timeline</h2><table><thead><tr><th>Assessment</th><th>Generated</th><th>Mode</th><th>Findings</th></tr></thead><tbody>{_timeline(entries)}</tbody></table></section>"""
    return _page(body, title=f"{project.name} monitoring")
