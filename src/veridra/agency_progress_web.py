# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .agency_navigation import agency_navigation
from .identity_tenancy import RequestIdentity
from .progress import ProgressSummary, build_progress_summary
from .project_store import ClientProject
from .request_security import require_request_identity
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency", tags=["agency-progress"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1040px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{border:1px solid #dfe3e8;border-radius:8px;padding:15px}.card span{display:block;color:#68707a;font-size:12px;text-transform:uppercase}.card strong{display:block;font-size:24px;margin-top:6px}.changes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.changes article{border:1px solid #dfe3e8;border-radius:8px;padding:16px}.changes ul{padding-left:20px;overflow-wrap:anywhere}.state-change{margin:0 0 10px;padding:10px;border:1px solid #e5e7eb;border-radius:7px}.back{display:inline-block;margin-bottom:12px;color:#22272d}@media(max-width:760px){.cards,.changes{grid-template-columns:1fr 1fr}}@media(max-width:520px){.cards,.changes{grid-template-columns:1fr}}
"""


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


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


def _items(values: tuple[str, ...]) -> str:
    if not values:
        return "<p class='muted'>None</p>"
    return "<ul>" + "".join(f"<li>{html.escape(value)}</li>" for value in values) + "</ul>"


def _change_groups(summary: ProgressSummary) -> str:
    return "".join(
        (
            f"<article><h2>Pages added <span class='muted'>({len(summary.pages_added)})</span></h2>{_items(summary.pages_added)}</article>",
            f"<article><h2>Pages removed <span class='muted'>({len(summary.pages_removed)})</span></h2>{_items(summary.pages_removed)}</article>",
            f"<article><h2>Pages changed <span class='muted'>({len(summary.pages_changed)})</span></h2>{_items(summary.pages_changed)}</article>",
            f"<article><h2>HTTP status changes <span class='muted'>({len(summary.page_status_changed)})</span></h2>{_items(summary.page_status_changed)}</article>",
            f"<article><h2>New findings <span class='muted'>({len(summary.new_findings)})</span></h2>{_items(summary.new_findings)}</article>",
            f"<article><h2>Resolved findings <span class='muted'>({len(summary.resolved_findings)})</span></h2>{_items(summary.resolved_findings)}</article>",
            f"<article><h2>Persistent findings <span class='muted'>({len(summary.persistent_findings)})</span></h2>{_items(summary.persistent_findings)}</article>",
        )
    )


def _state_changes(summary: ProgressSummary) -> str:
    if not summary.state_changes:
        return "<p class='muted'>No persisted finding changed status or severity.</p>"
    return "".join(
        "<div class='state-change'><strong>{identifier}</strong><br>"
        "Status: {before_status} → {after_status}<br>"
        "Severity: {before_severity} → {after_severity}</div>".format(
            identifier=html.escape(change.finding_id),
            before_status=html.escape(change.before_status),
            after_status=html.escape(change.after_status),
            before_severity=html.escape(change.before_severity),
            after_severity=html.escape(change.after_severity),
        )
        for change in summary.state_changes
    )


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


@router.get("/projects/{project_id}/progress", response_class=HTMLResponse)
def project_progress(project_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    project = _project(request, identity, project_id)
    history = TenantHistoryStore(_root(request))
    try:
        entries = history.list(identity, project_id)
    except TenantHistoryStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc

    navigation = agency_navigation(identity, current="projects")
    heading = (
        f"{navigation}<section><a class='back' href='/agency/projects/{html.escape(project_id, quote=True)}'>← Project overview</a>"
        f"<h1>Progress / Changes for {html.escape(project.name)}</h1>"
        f"<p class='muted'>Deterministic comparison of stored observations and stable finding identities. This surface does not infer traffic, rank or market performance.</p>"
    )
    if len(entries) < 2:
        body = heading + "<p class='notice'>At least two saved assessments are required before progress can be compared.</p></section>"
        return _page(f"{project.name} progress", body)

    latest = entries[0]
    previous = entries[1]
    try:
        before = history.load(identity, history.ref(identity, project_id, previous.id))
        after = history.load(identity, history.ref(identity, project_id, latest.id))
        comparison = history.compare(identity, project_id, previous.id, latest.id)
    except TenantHistoryStoreError as exc:
        raise HTTPException(status_code=404, detail="Assessment comparison not found.") from exc
    summary = build_progress_summary(before, after, comparison)

    page_notice = (
        "<p class='notice'>Page-level history is unavailable for this comparison because at least one assessment predates persisted page observations. Finding comparison remains valid.</p>"
        if not summary.page_history_available
        else ""
    )
    cards = "".join(
        (
            f"<div class='card'><span>Pages changed</span><strong>{len(summary.pages_changed)}</strong></div>",
            f"<div class='card'><span>New findings</span><strong>{len(summary.new_findings)}</strong></div>",
            f"<div class='card'><span>Resolved findings</span><strong>{len(summary.resolved_findings)}</strong></div>",
            f"<div class='card'><span>Persistent findings</span><strong>{len(summary.persistent_findings)}</strong></div>",
        )
    )
    body = (
        heading
        + f"<p><strong>Latest:</strong> {html.escape(latest.generated_at)}<br><strong>Previous:</strong> {html.escape(previous.generated_at)}</p>"
        + page_notice
        + f"</section><section><div class='cards'>{cards}</div></section>"
        + f"<section><h2>Change details</h2><div class='changes'>{_change_groups(summary)}</div></section>"
        + f"<section><h2>Finding state / severity changes</h2>{_state_changes(summary)}</section>"
    )
    return _page(f"{project.name} progress", body)
