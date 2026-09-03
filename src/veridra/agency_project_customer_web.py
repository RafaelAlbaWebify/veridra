# ruff: noqa: E501
from __future__ import annotations

import html
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .agency_conversion_web import tenant_project_next_actions as base_project_overview
from .agency_navigation import agency_navigation
from .customer_store import CustomerSourceType
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .project_delivery import (
    CustomerReviewState,
    DeliveryEvent,
    DeliveryMilestone,
    ProjectDeliveryRecord,
    RecurringServiceDecision,
)
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .tenant_customer_store import TenantCustomerStore
from .tenant_history_store import TenantHistoryStore
from .tenant_project_delivery_store import TenantProjectDeliveryStore
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency", tags=["agency-project-customer"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:980px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:90px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.success{border-left-color:#16794a;background:#f0faf5}.warning{border-left-color:#946200;background:#fff9e8}.actions{display:flex;gap:8px;flex-wrap:wrap}.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}.checklist{list-style:none;padding:0}.checklist li{padding:7px 0;border-bottom:1px solid #e8eaed}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}@media(max-width:700px){.row{grid-template-columns:1fr}}
"""


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _one(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Project delivery workflow is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Project delivery request is not permitted.") from exc


def _require_project_manager(identity: RequestIdentity) -> None:
    try:
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc


def _load_project(request: Request, identity: RequestIdentity, project_id: str) -> None:
    store = TenantProjectStore(_root(request))
    try:
        store.load(identity, store.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


def _linked_customers(request: Request, identity: RequestIdentity, project_id: str):
    return [
        (customer_id, customer)
        for customer_id, customer in TenantCustomerStore(_root(request)).list(identity)
        if project_id in customer.project_ids
    ]


def _change_request_link(request: Request, identity: RequestIdentity, project_id: str) -> str:
    for _customer_id, customer in _linked_customers(request, identity, project_id):
        if customer.source_type is CustomerSourceType.prospect:
            prospect_id = html.escape(customer.source_id, quote=True)
            return f"/agency/prospects/{prospect_id}/deal/change-requests"
    return "/agency/deals"


def _event(record: ProjectDeliveryRecord, action: str, reference: str = "") -> tuple[DeliveryEvent, ...]:
    return (*record.events, DeliveryEvent(action=action, reference=reference))


def _save_update(
    request: Request,
    identity: RequestIdentity,
    record: ProjectDeliveryRecord,
    updates: dict[str, object],
    *,
    action: str,
    reference: str = "",
) -> None:
    updates["events"] = _event(record, action, reference)
    try:
        updated = ProjectDeliveryRecord.model_validate(
            {**record.model_dump(mode="json"), **updates}
        )
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "Delivery transition is invalid.")
        raise HTTPException(status_code=400, detail=str(message)) from exc
    TenantProjectDeliveryStore(_root(request)).save(identity, updated)


def _status_label(value: str) -> str:
    return value.replace("_", " ").title()


def _deliverable_list(record: ProjectDeliveryRecord) -> str:
    if not record.deliverables:
        return "<p class='muted'>No deliverables configured yet.</p>"
    completed = set(record.completed_deliverables)
    return "<ul class='checklist'>" + "".join(
        f"<li>{'✓' if item in completed else '○'} {html.escape(item)}</li>"
        for item in record.deliverables
    ) + "</ul>"


def _history(record: ProjectDeliveryRecord) -> str:
    if not record.events:
        return "<p class='muted'>No delivery lifecycle events yet.</p>"
    return "<ul class='checklist'>" + "".join(
        f"<li><strong>{html.escape(_status_label(item.action))}</strong> · {html.escape(item.at.isoformat())}"
        + (f"<br><span class='muted'>{html.escape(item.reference)}</span>" if item.reference else "")
        + "</li>"
        for item in reversed(record.events)
    ) + "</ul>"


def _delivery_actions(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
    record: ProjectDeliveryRecord,
) -> str:
    project_id_html = html.escape(project_id, quote=True)
    base = f"/agency/projects/{project_id_html}/delivery"
    change_link = html.escape(_change_request_link(request, identity, project_id), quote=True)
    if record.milestone is DeliveryMilestone.working:
        return f"""
<section><h2>Delivery setup</h2><form method='post' action='{base}/configure'>
<label>Customer-facing deliverables — one per line</label><textarea name='deliverables' required>{html.escape(chr(10).join(record.deliverables))}</textarea>
<div class='row'><div><label>Revision policy/reference</label><input name='revision_policy' maxlength='2000' value='{html.escape(record.revision_policy, quote=True)}'></div><div><label>Included revisions</label><input type='number' name='included_revisions' min='0' max='100' value='{record.included_revisions}'></div></div>
<label>Acceptance criteria</label><textarea name='acceptance_criteria' required>{html.escape(record.acceptance_criteria)}</textarea>
<label><input type='checkbox' name='final_balance_required' value='yes' {'checked' if record.final_balance_required else ''}> Final balance evidence is required before closure</label>
<button type='submit'>Save delivery setup</button></form></section>
<section><h2>Ready for customer review?</h2><p class='muted'>This confirms every configured deliverable is complete and starts customer review.</p><form method='post' action='{base}/ready'><button type='submit'>Mark deliverables complete & request review</button></form></section>"""
    if record.milestone is DeliveryMilestone.ready_for_review:
        if record.review_state is CustomerReviewState.unresponsive:
            return f"<section><h2>Customer review — unresponsive</h2><p class='notice warning'>The project remains open. Resume review when the customer responds; do not close it as accepted.</p><form method='post' action='{base}/resume-review'><button type='submit'>Resume customer review</button></form></section>"
        if record.review_state is CustomerReviewState.blocked:
            return f"<section><h2>Customer review — blocked</h2><form method='post' action='{base}/resume-review'><button type='submit'>Resume customer review</button></form></section>"
        return f"""<section><h2>Customer review</h2><div class='row'><form method='post' action='{base}/changes-requested'><label>Included revision request/reference</label><textarea name='reference' required></textarea><button type='submit'>Record changes requested</button></form><form method='post' action='{base}/accept'><label>Acceptance evidence/reference</label><textarea name='reference' required></textarea><button type='submit'>Record customer acceptance</button></form></div><div class='row'><form method='post' action='{base}/unresponsive'><label>Follow-up evidence/reference</label><input name='reference' required><button class='secondary' type='submit'>Mark unresponsive</button></form><form method='post' action='{base}/blocked'><label>Blocker/reference</label><input name='reference' required><button class='secondary' type='submit'>Mark blocked</button></form></div><p><a class='button secondary' href='{change_link}'>Out-of-scope change request</a></p></section>"""
    if record.milestone is DeliveryMilestone.revision_in_progress:
        return f"<section><h2>Revision in progress</h2><p><strong>Revision use:</strong> {record.revisions_used}/{record.included_revisions}</p><form method='post' action='{base}/revision-completed'><label>Revision completion evidence/reference</label><textarea name='reference' required></textarea><button type='submit'>Complete revision & return to review</button></form><p><a class='button secondary' href='{change_link}'>Out-of-scope change request</a></p></section>"
    if record.milestone is DeliveryMilestone.accepted:
        return f"<section><h2>Customer accepted</h2><p class='notice success'>Acceptance is evidenced. Start the handoff checklist next.</p><form method='post' action='{base}/start-handoff'><button type='submit'>Start handoff</button></form></section>"
    if record.milestone is DeliveryMilestone.handoff:
        return f"""<section><h2>Handoff checklist</h2><form method='post' action='{base}/handoff-complete'><label><input type='checkbox' name='backups' value='yes' required> Backups retained/confirmed</label><label><input type='checkbox' name='access' value='yes' required> Ownership and access transferred/confirmed</label><label><input type='checkbox' name='documentation' value='yes' required> Documentation/training completed where applicable</label><label>Handoff evidence/reference</label><textarea name='reference' required></textarea><button type='submit'>Complete handoff</button></form></section>"""
    if record.milestone is DeliveryMilestone.final_balance:
        return f"""<section><h2>Final completion gate</h2><form method='post' action='{base}/close'><label>Completion summary</label><textarea name='completion_summary' required></textarea>{"<label>Final invoice/balance evidence</label><input name='final_balance_evidence' required>" if record.final_balance_required else "<p class='muted'>No final balance evidence is required for this project.</p>"}<label>Recurring-service decision</label><select name='recurring_decision' required><option value=''>Choose…</option><option value='offered'>Offered — awaiting decision</option><option value='accepted'>Accepted</option><option value='declined'>Declined</option><option value='not_applicable'>Not applicable</option></select><button type='submit'>Close project</button></form></section>"""
    return f"""<section><h2>Project closed</h2><p class='notice success'>Delivery, customer acceptance, handoff and the completion gate are recorded.</p><p><strong>Recurring service:</strong> {html.escape(_status_label(record.recurring_decision.value))}</p><form method='post' action='{base}/reopen'><label>Reason/evidence for reopening</label><textarea name='reference' required></textarea><button class='secondary' type='submit'>Reopen delivery</button></form><p><a class='button secondary' href='{change_link}'>Open change request instead</a></p></section>"""


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_overview_with_customer(
    project_id: str,
    request: Request,
    task_created: str | None = None,
) -> str:
    identity = require_request_identity(request)
    rendered = base_project_overview(project_id, request, task_created)
    root = _root(request)
    customers = TenantCustomerStore(root).list(identity)
    linked = [
        (customer_id, customer)
        for customer_id, customer in customers
        if project_id in customer.project_ids
    ]
    if not linked:
        relationship = "<p class='notice'><strong>Customer relationship:</strong> Not linked. Link this project from the customer record before treating it as customer delivery work.</p>"
    else:
        links = " · ".join(
            f"<a href='/agency/customers/{html.escape(customer_id, quote=True)}'>{html.escape(customer.business_name)}</a>"
            for customer_id, customer in linked
        )
        relationship = f"<p class='notice'><strong>Customer:</strong> {links}</p>"
    assessments = TenantHistoryStore(root).list(identity, project_id)
    project_id_html = html.escape(project_id, quote=True)
    delivery = TenantProjectDeliveryStore(root).load_or_empty(identity, project_id)
    delivery_link = (
        f"<p><a href='/agency/projects/{project_id_html}/delivery'>Delivery & closure</a> · "
        f"<span class='muted'>Status: {html.escape(_status_label(delivery.milestone.value))}</span></p>"
    )
    if assessments:
        project_tools = (
            f"<p><a href='/agency/projects/{project_id_html}/progress'>Progress / Changes</a> · "
            f"<a href='/agency/projects/{project_id_html}/ai-review'>AI review exchange</a></p>"
        )
    else:
        project_tools = (
            "<p class='muted'>Progress / Changes and AI review become available after the first saved assessment.</p>"
        )
    marker = "<h1>"
    return rendered.replace(marker, relationship + delivery_link + project_tools + marker, 1)


@router.get("/projects/{project_id}/delivery", response_class=HTMLResponse)
def project_delivery(project_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    _load_project(request, identity, project_id)
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    project_id_html = html.escape(project_id, quote=True)
    accepted = html.escape(record.accepted_at.isoformat()) if record.accepted_at else "Not yet"
    closed = html.escape(record.closed_at.isoformat()) if record.closed_at else "Not yet"
    body = f"""{agency_navigation(identity, current='projects')}<section><p><a href='/agency/projects/{project_id_html}'>← Project overview</a></p><h1>Delivery & closure</h1><p><span class='badge'>{html.escape(_status_label(record.milestone.value))}</span> <span class='badge'>{html.escape(_status_label(record.review_state.value))}</span></p><p><strong>Accepted:</strong> {accepted}<br><strong>Closed:</strong> {closed}<br><strong>Revisions:</strong> {record.revisions_used}/{record.included_revisions}</p></section><section><h2>Customer-facing deliverables</h2>{_deliverable_list(record)}<p><strong>Revision policy:</strong> {html.escape(record.revision_policy or 'Not set')}<br><strong>Acceptance criteria:</strong> {html.escape(record.acceptance_criteria or 'Not set')}</p></section>{_delivery_actions(request, identity, project_id, record)}<section><h2>Lifecycle evidence</h2>{_history(record)}</section>"""
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Delivery & closure</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


@router.post("/projects/{project_id}/delivery/configure")
async def configure_delivery(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    _load_project(request, identity, project_id)
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.working:
        raise HTTPException(status_code=409, detail="Delivery setup can only be edited while work is open.")
    body = await request.body()
    deliverables = tuple(line.strip() for line in _one(body, "deliverables").splitlines() if line.strip())
    if not deliverables:
        raise HTTPException(status_code=400, detail="At least one customer-facing deliverable is required.")
    try:
        included = int(_one(body, "included_revisions") or "0")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Included revision count is invalid.") from exc
    _save_update(request, identity, record, {
        "deliverables": deliverables,
        "completed_deliverables": (),
        "revision_policy": _one(body, "revision_policy"),
        "included_revisions": included,
        "acceptance_criteria": _one(body, "acceptance_criteria"),
        "final_balance_required": _one(body, "final_balance_required") == "yes",
    }, action="delivery_setup_saved")
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/ready")
def delivery_ready(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    _load_project(request, identity, project_id)
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.working:
        raise HTTPException(status_code=409, detail="Delivery is not in an open working state.")
    _save_update(request, identity, record, {
        "completed_deliverables": record.deliverables,
        "milestone": DeliveryMilestone.ready_for_review,
        "review_state": CustomerReviewState.awaiting_review,
    }, action="delivery_ready")
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/changes-requested")
async def changes_requested(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    body = await request.body()
    reference = _one(body, "reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Revision request evidence/reference is required.")
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.ready_for_review or record.review_state is not CustomerReviewState.awaiting_review:
        raise HTTPException(status_code=409, detail="The project is not awaiting customer review.")
    next_count = record.revisions_used + 1
    if next_count > record.included_revisions:
        raise HTTPException(status_code=409, detail="Included revisions are exhausted. Record an approved out-of-scope Change Request instead.")
    _save_update(request, identity, record, {
        "milestone": DeliveryMilestone.revision_in_progress,
        "review_state": CustomerReviewState.changes_requested,
        "review_reference": reference,
        "revisions_used": next_count,
    }, action="changes_requested", reference=reference)
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/revision-completed")
async def revision_completed(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    reference = _one(await request.body(), "reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Revision completion evidence/reference is required.")
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.revision_in_progress:
        raise HTTPException(status_code=409, detail="No included revision is in progress.")
    _save_update(request, identity, record, {
        "milestone": DeliveryMilestone.ready_for_review,
        "review_state": CustomerReviewState.awaiting_review,
        "review_reference": reference,
    }, action="revision_completed", reference=reference)
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


async def _review_hold(project_id: str, request: Request, state: CustomerReviewState, action: str) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    reference = _one(await request.body(), "reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Review evidence/reference is required.")
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.ready_for_review:
        raise HTTPException(status_code=409, detail="The project is not in customer review.")
    _save_update(request, identity, record, {"review_state": state, "review_reference": reference}, action=action, reference=reference)
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/unresponsive")
async def customer_unresponsive(project_id: str, request: Request) -> RedirectResponse:
    return await _review_hold(project_id, request, CustomerReviewState.unresponsive, "customer_unresponsive")


@router.post("/projects/{project_id}/delivery/blocked")
async def customer_review_blocked(project_id: str, request: Request) -> RedirectResponse:
    return await _review_hold(project_id, request, CustomerReviewState.blocked, "customer_review_blocked")


@router.post("/projects/{project_id}/delivery/resume-review")
def resume_review(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.ready_for_review or record.review_state not in {CustomerReviewState.unresponsive, CustomerReviewState.blocked}:
        raise HTTPException(status_code=409, detail="Customer review is not paused.")
    _save_update(request, identity, record, {"review_state": CustomerReviewState.awaiting_review}, action="review_resumed")
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/accept")
async def customer_accept(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    reference = _one(await request.body(), "reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Customer acceptance evidence/reference is required.")
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.ready_for_review or record.review_state is not CustomerReviewState.awaiting_review:
        raise HTTPException(status_code=409, detail="The project is not awaiting customer acceptance.")
    now = datetime.now(UTC)
    _save_update(request, identity, record, {
        "milestone": DeliveryMilestone.accepted,
        "review_state": CustomerReviewState.accepted,
        "acceptance_evidence": reference,
        "accepted_at": now,
    }, action="customer_accepted", reference=reference)
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/start-handoff")
def start_handoff(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.accepted:
        raise HTTPException(status_code=409, detail="Customer acceptance is required before handoff.")
    _save_update(request, identity, record, {"milestone": DeliveryMilestone.handoff}, action="handoff_started")
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/handoff-complete")
async def handoff_complete(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    body = await request.body()
    reference = _one(body, "reference")
    if not reference or any(_one(body, name) != "yes" for name in ("backups", "access", "documentation")):
        raise HTTPException(status_code=400, detail="All handoff items and handoff evidence are required.")
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.handoff:
        raise HTTPException(status_code=409, detail="Handoff has not started.")
    _save_update(request, identity, record, {
        "milestone": DeliveryMilestone.final_balance,
        "handoff_backups": True,
        "handoff_access": True,
        "handoff_documentation": True,
        "handoff_reference": reference,
    }, action="handoff_completed", reference=reference)
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/close")
async def close_delivery(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    body = await request.body()
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.final_balance:
        raise HTTPException(status_code=409, detail="Handoff must be complete before project closure.")
    try:
        recurring = RecurringServiceDecision(_one(body, "recurring_decision"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="A recurring-service decision is required.") from exc
    if recurring is RecurringServiceDecision.undecided:
        raise HTTPException(status_code=400, detail="A recurring-service decision is required.")
    now = datetime.now(UTC)
    _save_update(request, identity, record, {
        "completion_summary": _one(body, "completion_summary"),
        "final_balance_evidence": _one(body, "final_balance_evidence"),
        "recurring_decision": recurring,
        "milestone": DeliveryMilestone.closed,
        "closed_at": now,
    }, action="project_closed", reference=_one(body, "final_balance_evidence"))
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)


@router.post("/projects/{project_id}/delivery/reopen")
async def reopen_delivery(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    _require_project_manager(identity)
    _trusted_origin(request)
    reference = _one(await request.body(), "reference")
    if not reference:
        raise HTTPException(status_code=400, detail="A reopen reason/evidence reference is required.")
    record = TenantProjectDeliveryStore(_root(request)).load_or_empty(identity, project_id)
    if record.milestone is not DeliveryMilestone.closed:
        raise HTTPException(status_code=409, detail="Only a closed project can be reopened.")
    _save_update(request, identity, record, {
        "milestone": DeliveryMilestone.working,
        "review_state": CustomerReviewState.not_requested,
        "completed_deliverables": (),
        "closed_at": None,
        "reopened_at": datetime.now(UTC),
        "reopen_reference": reference,
        "recurring_decision": RecurringServiceDecision.undecided,
    }, action="project_reopened", reference=reference)
    return RedirectResponse(f"/agency/projects/{project_id}/delivery", status_code=303)
