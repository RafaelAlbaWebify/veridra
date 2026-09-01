# ruff: noqa: E501
from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .agency_navigation import agency_navigation
from .ai_review_exchange import (
    AIReviewExchangeError,
    ReviewContextType,
    parse_and_validate_result,
)
from .identity_tenancy import IdentityBoundaryError, RequestIdentity, TenantCapability, require_tenant_capability
from .project_ai_review import build_project_review_bundle
from .project_store import ClientProject
from .request_security import require_request_identity
from .tenant_ai_review_store import TenantAIReviewStore, TenantAIReviewStoreError
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency", tags=["agency-ai-review"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:980px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}.actions{display:flex;gap:8px;flex-wrap:wrap}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.ai{border-left-color:#6b4eff;background:#f7f5ff}.error{border-left-color:#b42318;background:#fff4f2}textarea{width:100%;min-height:360px;padding:12px;border:1px solid #cfd4da;border-radius:7px;font:12px Consolas,monospace}ul{padding-left:20px}.history{width:100%;border-collapse:collapse}.history th,.history td{text-align:left;padding:9px;border-bottom:1px solid #e5e7eb;vertical-align:top}.pill{display:inline-block;padding:3px 7px;border-radius:999px;background:#eee;font-size:12px}code{overflow-wrap:anywhere}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _project(request: Request, identity: RequestIdentity, project_id: str) -> ClientProject:
    store = TenantProjectStore(_root(request))
    try:
        return store.load(identity, store.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


def _can_manage(identity: RequestIdentity) -> bool:
    try:
        require_tenant_capability(identity, TenantCapability.manage_reports)
    except IdentityBoundaryError:
        return False
    return True


def _latest_bundle(request: Request, identity: RequestIdentity, project_id: str):
    project = _project(request, identity, project_id)
    history = TenantHistoryStore(_root(request))
    try:
        entries = history.list(identity, project_id)
    except TenantHistoryStoreError as exc:
        raise HTTPException(status_code=404, detail="Project history not found.") from exc
    if not entries:
        raise HTTPException(status_code=409, detail="Run and save an assessment before exporting an AI review bundle.")
    latest = entries[0]
    try:
        assessment = history.load(identity, history.ref(identity, project_id, latest.id))
    except TenantHistoryStoreError as exc:
        raise HTTPException(status_code=404, detail="Latest assessment not found.") from exc
    return build_project_review_bundle(
        project_id=project_id,
        project=project,
        assessment_id=latest.id,
        assessment=assessment,
    )


def _list(values: tuple[str, ...]) -> str:
    if not values:
        return "<p class='muted'>None recorded.</p>"
    return "<ul>" + "".join(f"<li>{html.escape(value)}</li>" for value in values) + "</ul>"


@router.get("/projects/{project_id}/ai-review", response_class=HTMLResponse)
def project_ai_review(project_id: str, request: Request, imported: bool = False) -> str:
    identity = require_request_identity(request)
    project = _project(request, identity, project_id)
    store = TenantAIReviewStore(_root(request))
    history = store.list_results(identity, ReviewContextType.project, project_id)
    can_manage = _can_manage(identity)
    actions = [
        f"<a class='button' href='/agency/projects/{html.escape(project_id, quote=True)}/ai-review/export'>Export AI review JSON</a>"
    ]
    if can_manage:
        actions.append(
            f"<a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/ai-review/import'>Import reviewed result</a>"
        )
    rows = "".join(
        "<tr>"
        f"<td><a href='/agency/projects/{html.escape(project_id, quote=True)}/ai-review/results/{html.escape(item.review_id, quote=True)}'>{html.escape(item.review_id)}</a></td>"
        f"<td>{html.escape(item.generated_at)}</td>"
        f"<td><code>{html.escape(item.source_bundle_id)}</code></td>"
        f"<td>{html.escape(item.model_provenance or 'Not supplied')}</td>"
        "</tr>"
        for item in history
    ) or "<tr><td colspan='4' class='muted'>No reviewed result has been imported yet.</td></tr>"
    imported_notice = "<p class='notice ai'><strong>Reviewed result imported.</strong> AI reasoning is stored as a separate provenance layer; deterministic VERIDRA evidence was not changed.</p>" if imported else ""
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects/{html.escape(project_id, quote=True)}'>← Project overview</a></p><h1>AI review exchange — {html.escape(project.name)}</h1>{imported_notice}<p class='notice ai'><strong>Separation rule:</strong> VERIDRA owns observed evidence and deterministic state. Imported AI reasoning is advisory and visibly separate.</p><div class='actions'>{''.join(actions)}</div><p class='muted'>Normal workflow: export one JSON → attach it to ChatGPT with the standard prompt → import the returned JSON → inspect the reviewed result.</p></section><section><h2>Review history / provenance</h2><table class='history'><thead><tr><th>Review</th><th>Generated</th><th>Source bundle</th><th>Model provenance</th></tr></thead><tbody>{rows}</tbody></table></section>"""
    return _page(f"{project.name} AI review", body)


@router.get("/projects/{project_id}/ai-review/export")
def export_project_ai_review(project_id: str, request: Request) -> Response:
    identity = require_request_identity(request)
    require_tenant_capability(identity, TenantCapability.manage_reports)
    bundle = _latest_bundle(request, identity, project_id)
    TenantAIReviewStore(_root(request)).save_bundle(identity, bundle)
    content = json.dumps(bundle.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True)
    filename = f"VERIDRA_AI_REVIEW_{project_id}_{bundle.bundle_id}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/projects/{project_id}/ai-review/import", response_class=HTMLResponse)
def import_project_ai_review_form(project_id: str, request: Request, error: str | None = None) -> str:
    identity = require_request_identity(request)
    require_tenant_capability(identity, TenantCapability.manage_reports)
    project = _project(request, identity, project_id)
    error_panel = f"<p class='notice error'>{html.escape(error)}</p>" if error else ""
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects/{html.escape(project_id, quote=True)}/ai-review'>← AI review exchange</a></p><h1>Import reviewed result</h1>{error_panel}<p>Paste the complete <code>veridra_ai_review_result</code> JSON returned for this project. VERIDRA validates schema, source bundle id/hash, chronology, result integrity and evidence references before storing it.</p><form method='post'><label for='result_json'><strong>Reviewed result JSON</strong></label><textarea id='result_json' name='result_json' required spellcheck='false'></textarea><p><button type='submit'>Validate and import</button></p></form><p class='muted'>Import is append-only. It cannot overwrite assessments, findings, deterministic scores, customer records, prospects or outreach state.</p></section>"""
    return _page(f"Import AI review — {project.name}", body)


@router.post("/projects/{project_id}/ai-review/import")
async def import_project_ai_review(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    require_tenant_capability(identity, TenantCapability.manage_reports)
    _project(request, identity, project_id)
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    raw = values.get("result_json", [""])[0].strip()
    try:
        preview = json.loads(raw)
        if not isinstance(preview, dict):
            raise ValueError
        bundle_id = str(preview.get("source_bundle_id", ""))
        if not bundle_id:
            raise ValueError
        store = TenantAIReviewStore(_root(request))
        bundle = store.load_bundle(identity, ReviewContextType.project, project_id, bundle_id)
        result = parse_and_validate_result(raw, source_bundle=bundle)
        store.save_result(identity, bundle=bundle, result=result)
    except (ValueError, AIReviewExchangeError, TenantAIReviewStoreError) as exc:
        message = str(exc) or "Reviewed result is invalid."
        location = f"/agency/projects/{project_id}/ai-review/import?error={html.escape(message, quote=True)}"
        return RedirectResponse(location, status_code=303)
    return RedirectResponse(f"/agency/projects/{project_id}/ai-review?imported=true", status_code=303)


@router.get("/projects/{project_id}/ai-review/results/{review_id}", response_class=HTMLResponse)
def view_project_ai_review(project_id: str, review_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    project = _project(request, identity, project_id)
    store = TenantAIReviewStore(_root(request))
    try:
        result = store.load_result(identity, ReviewContextType.project, project_id, review_id)
    except TenantAIReviewStoreError as exc:
        raise HTTPException(status_code=404, detail="AI reviewed result not found.") from exc
    actions = "".join(
        f"<li><span class='pill'>{html.escape(item.action.value)}</span> {html.escape(item.reason)}"
        + (f"<br><span class='muted'>Evidence: {html.escape(', '.join(item.evidence_refs))}</span>" if item.evidence_refs else "")
        + "</li>"
        for item in result.safe_actions
    ) or "<li class='muted'>No structured safe actions supplied.</li>"
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects/{html.escape(project_id, quote=True)}/ai-review'>← AI review exchange</a></p><h1>Reviewed result — {html.escape(project.name)}</h1><p class='notice ai'><strong>AI interpretation — imported reasoning, not VERIDRA observation.</strong> Verify recommendations against the cited deterministic evidence before acting.</p><p><strong>Review ID:</strong> <code>{html.escape(result.review_id)}</code><br><strong>Generated:</strong> {html.escape(result.generated_at.isoformat())}<br><strong>Model:</strong> {html.escape(result.model_provenance or 'Not supplied')}<br><strong>Tool:</strong> {html.escape(result.tool_provenance or 'Not supplied')}<br><strong>Source bundle:</strong> <code>{html.escape(result.source_bundle_id)}</code><br><strong>Confidence:</strong> {html.escape(result.confidence.value)}</p></section><section><h2>Interpretation</h2><p>{html.escape(result.interpretation)}</p><h3>Strengths</h3>{_list(result.strengths)}<h3>Weaknesses / gaps</h3>{_list(result.weaknesses_gaps)}<h3>Opportunity assessment</h3><p>{html.escape(result.opportunity_assessment)}</p><h3>Uncertainty</h3>{_list(result.uncertainty)}</section><section><h2>Recommended next action</h2><p>{html.escape(result.recommended_next_action)}</p><h3>Suggested messaging / positioning</h3>{_list(result.suggested_messaging_positioning)}<p class='muted'>These are imported suggestions. No outreach has been sent and no source workflow state is automatically modified.</p></section><section><h2>Structured safe actions</h2><ul>{actions}</ul><p class='muted'>Imported as review metadata only; execution remains an explicit operator decision.</p></section>"""
    return _page(f"AI review {result.review_id}", body)
