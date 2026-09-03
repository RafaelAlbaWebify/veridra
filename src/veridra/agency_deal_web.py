# ruff: noqa: E501
from __future__ import annotations

import html
import os
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .agency_navigation import agency_navigation
from .deal_lifecycle import (
    DiscoveryRequirements,
    ProposalStatus,
    ProposalVersion,
    ReplyOutcome,
)
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .prospect import Prospect, ProspectStatus
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .tenant_deal_store import TenantDealStore, TenantDealStoreError
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError

router = APIRouter(tags=["agency-deal"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1180px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.success{border-left-color:#247a3c;background:#f2fbf4}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.actions{display:flex;gap:8px;flex-wrap:wrap}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:90px}.proposal{border:1px solid #e1e5ea;border-radius:8px;padding:16px;margin:12px 0}.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}@media(max-width:760px){.row{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _identity(request: Request) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_leads)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    return identity


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Sales workflow is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Sales workflow request is not permitted.") from exc


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _load_prospect(request: Request, identity: RequestIdentity, prospect_id: str) -> Prospect:
    store = TenantProspectStore(_root(request))
    try:
        return store.load(identity, store.ref(identity, prospect_id))
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc


def _sync_prospect(
    request: Request,
    identity: RequestIdentity,
    prospect_id: str,
    *,
    status: ProspectStatus,
    next_action: str,
) -> None:
    store = TenantProspectStore(_root(request))
    prospect = _load_prospect(request, identity, prospect_id)
    updated = Prospect.model_validate(
        {
            **prospect.model_dump(mode="json"),
            "status": status,
            "next_action": next_action,
            "updated_at": datetime.now(UTC),
        }
    )
    try:
        store.replace(identity, store.ref(identity, prospect_id), updated)
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=409, detail="Prospect stage could not be synchronized.") from exc


def _reply_options(current: ReplyOutcome | None) -> str:
    return "<option value=''>Not recorded</option>" + "".join(
        f"<option value='{item.value}'{' selected' if current is item else ''}>{item.value.replace('_', ' ').title()}</option>"
        for item in ReplyOutcome
    )


def _proposal_cards(prospect_id: str, proposals: tuple[ProposalVersion, ...]) -> str:
    if not proposals:
        return "<p class='notice'>No proposal versions yet. Complete discovery before creating a bounded quote.</p>"
    cards: list[str] = []
    for item in reversed(proposals):
        recurring = (
            f" · recurring {item.currency} {item.recurring_amount:.2f} {html.escape(item.recurring_cadence)}"
            if item.recurring_amount is not None
            else ""
        )
        acceptance = (
            f"<p><strong>Acceptance evidence:</strong> {html.escape(item.acceptance_reference)}</p>"
            if item.acceptance_reference
            else ""
        )
        status_options = "".join(
            f"<option value='{status.value}'{' selected' if item.status is status else ''}>{status.value.title()}</option>"
            for status in ProposalStatus
        )
        cards.append(
            f"<div class='proposal'><h3>v{item.version} — {html.escape(item.title)} <span class='badge'>{html.escape(item.status.value)}</span></h3>"
            f"<p><strong>Price:</strong> {html.escape(item.currency)} {item.price_amount:.2f}{recurring}<br><strong>Valid until:</strong> {item.valid_until.isoformat()}<br><strong>Timeline:</strong> {html.escape(item.timeline)}</p>"
            f"<p><strong>Scope:</strong> {html.escape(item.scope)}</p><p><strong>Deliverables:</strong> {html.escape(item.deliverables)}</p>"
            f"<p><strong>Exclusions:</strong> {html.escape(item.exclusions or 'None recorded')}</p>{acceptance}"
            f"<form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/deal/proposals/{item.version}/status'><div class='row'><div><label>Status</label><select name='status'>{status_options}</select></div><div><label>Acceptance evidence/reference</label><input name='acceptance_reference' maxlength='1000' value='{html.escape(item.acceptance_reference, quote=True)}' placeholder='Required when accepting'></div></div><button type='submit'>Update proposal status</button></form></div>"
        )
    return "".join(cards)


@router.get("/agency/prospects/{prospect_id}/deal", response_class=HTMLResponse)
def deal_page(prospect_id: str, request: Request) -> str:
    identity = _identity(request)
    prospect = _load_prospect(request, identity, prospect_id)
    deal = TenantDealStore(_root(request)).load_or_empty(identity, prospect_id)
    navigation = agency_navigation(identity, current="prospects")
    discovery = deal.discovery
    accepted = "<p class='notice success'><strong>Proposal accepted.</strong> Next gate: agreement and payment evidence before work starts.</p>" if deal.has_accepted_proposal else ""
    body = f"{navigation}<section><p><a href='/agency/prospects/{html.escape(prospect_id, quote=True)}'>← Prospect</a></p><h1>Sales / proposal — {html.escape(prospect.business_name)}</h1><p class='muted'>VERIDRA records the commercial process and evidence. Email/calls and signatures remain external unless explicitly integrated later.</p>{accepted}</section>"
    body += f"<section><h2>1. Reply / conversation</h2><form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/deal/reply'><label>Reply outcome</label><select name='reply_outcome'>{_reply_options(deal.reply_outcome)}</select><label>Conversation summary</label><textarea name='conversation_summary' maxlength='4000'>{html.escape(deal.conversation_summary)}</textarea><label>Next action</label><input name='next_action' maxlength='1000' value='{html.escape(deal.next_action, quote=True)}'><button type='submit'>Save reply context</button></form></section>"
    body += f"<section><h2>2. Discovery / requirements</h2><p class='muted'>Capture facts needed to define a bounded service. Do not store passwords or secrets here.</p><form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/deal/discovery'><label>Business goals</label><textarea name='goals' required>{html.escape(discovery.goals if discovery else '')}</textarea><div class='row'><div><label>Current platform</label><input name='current_platform' value='{html.escape(discovery.current_platform if discovery else '', quote=True)}'></div><div><label>Hosting</label><input name='hosting' value='{html.escape(discovery.hosting if discovery else '', quote=True)}'></div></div><div class='row'><div><label>Decision maker</label><input name='decision_maker' value='{html.escape(discovery.decision_maker if discovery else '', quote=True)}'></div><div><label>Urgency</label><input name='urgency' value='{html.escape(discovery.urgency if discovery else '', quote=True)}'></div></div><label>Constraints</label><textarea name='constraints'>{html.escape(discovery.constraints if discovery else '')}</textarea><label>Access readiness</label><textarea name='access_readiness'>{html.escape(discovery.access_readiness if discovery else '')}</textarea><label>Measurable scope</label><textarea name='measurable_scope' required>{html.escape(discovery.measurable_scope if discovery else '')}</textarea><label>Deliverables</label><textarea name='deliverables' required>{html.escape(discovery.deliverables if discovery else '')}</textarea><label>Exclusions</label><textarea name='exclusions'>{html.escape(discovery.exclusions if discovery else '')}</textarea><label>Assumptions</label><textarea name='assumptions'>{html.escape(discovery.assumptions if discovery else '')}</textarea><label>Timeline</label><input name='timeline' required value='{html.escape(discovery.timeline if discovery else '', quote=True)}'><button type='submit'>Save discovery</button></form></section>"
    disabled_note = "" if discovery else "<p class='notice'>Complete discovery before drafting a proposal.</p>"
    body += f"<section><h2>3. Proposal / quote</h2>{disabled_note}<form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/deal/proposals'><label>Proposal title</label><input name='title' required placeholder='Website Improvement Sprint'><label>Scope</label><textarea name='scope' required>{html.escape(discovery.measurable_scope if discovery else '')}</textarea><label>Deliverables</label><textarea name='deliverables' required>{html.escape(discovery.deliverables if discovery else '')}</textarea><label>Exclusions</label><textarea name='exclusions'>{html.escape(discovery.exclusions if discovery else '')}</textarea><label>Assumptions</label><textarea name='assumptions'>{html.escape(discovery.assumptions if discovery else '')}</textarea><div class='row'><div><label>Timeline</label><input name='timeline' required value='{html.escape(discovery.timeline if discovery else '', quote=True)}'></div><div><label>Valid until</label><input name='valid_until' type='date' required></div></div><div class='row'><div><label>One-off price</label><input name='price_amount' type='number' step='0.01' min='0.01' required></div><div><label>Currency</label><input name='currency' maxlength='3' placeholder='EUR' required></div></div><div class='row'><div><label>Recurring amount (optional)</label><input name='recurring_amount' type='number' step='0.01' min='0.01'></div><div><label>Recurring cadence</label><input name='recurring_cadence' placeholder='monthly'></div></div><button type='submit'>Create proposal version</button></form>{_proposal_cards(prospect_id, deal.proposals)}</section>"
    return _page(f"Sales / proposal — {prospect.business_name}", body)


@router.post("/agency/prospects/{prospect_id}/deal/reply")
async def save_reply(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    _load_prospect(request, identity, prospect_id)
    values = _values(await request.body())
    outcome_raw = _one(values, "reply_outcome")
    try:
        outcome = ReplyOutcome(outcome_raw) if outcome_raw else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown reply outcome.") from exc
    store = TenantDealStore(_root(request))
    deal = store.load_or_empty(identity, prospect_id).model_copy(
        update={
            "reply_outcome": outcome,
            "conversation_summary": _one(values, "conversation_summary"),
            "next_action": _one(values, "next_action"),
        }
    )
    try:
        store.save(identity, deal)
    except TenantDealStoreError as exc:
        raise HTTPException(status_code=500, detail="Reply context could not be saved.") from exc
    if outcome is not None:
        _sync_prospect(
            request,
            identity,
            prospect_id,
            status=ProspectStatus.responded,
            next_action=deal.next_action or "Review reply and complete discovery",
        )
    return RedirectResponse(f"/agency/prospects/{prospect_id}/deal", status_code=303)


@router.post("/agency/prospects/{prospect_id}/deal/discovery")
async def save_discovery(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    _load_prospect(request, identity, prospect_id)
    values = _values(await request.body())
    try:
        discovery = DiscoveryRequirements(
            goals=_one(values, "goals"),
            current_platform=_one(values, "current_platform"),
            hosting=_one(values, "hosting"),
            decision_maker=_one(values, "decision_maker"),
            urgency=_one(values, "urgency"),
            constraints=_one(values, "constraints"),
            access_readiness=_one(values, "access_readiness"),
            measurable_scope=_one(values, "measurable_scope"),
            deliverables=_one(values, "deliverables"),
            exclusions=_one(values, "exclusions"),
            assumptions=_one(values, "assumptions"),
            timeline=_one(values, "timeline"),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Discovery requirements are incomplete.") from exc
    store = TenantDealStore(_root(request))
    deal = store.load_or_empty(identity, prospect_id).model_copy(update={"discovery": discovery})
    store.save(identity, deal)
    _sync_prospect(
        request,
        identity,
        prospect_id,
        status=ProspectStatus.conversation,
        next_action="Prepare bounded proposal/quote",
    )
    return RedirectResponse(f"/agency/prospects/{prospect_id}/deal", status_code=303)


@router.post("/agency/prospects/{prospect_id}/deal/proposals")
async def create_proposal(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    _load_prospect(request, identity, prospect_id)
    store = TenantDealStore(_root(request))
    deal = store.load_or_empty(identity, prospect_id)
    if deal.discovery is None:
        raise HTTPException(status_code=409, detail="Complete discovery before creating a proposal.")
    values = _values(await request.body())
    recurring_raw = _one(values, "recurring_amount")
    try:
        proposal = ProposalVersion(
            version=len(deal.proposals) + 1,
            title=_one(values, "title"),
            scope=_one(values, "scope"),
            deliverables=_one(values, "deliverables"),
            exclusions=_one(values, "exclusions"),
            assumptions=_one(values, "assumptions"),
            timeline=_one(values, "timeline"),
            price_amount=float(_one(values, "price_amount")),
            currency=_one(values, "currency").upper(),
            recurring_amount=float(recurring_raw) if recurring_raw else None,
            recurring_cadence=_one(values, "recurring_cadence"),
            valid_until=date.fromisoformat(_one(values, "valid_until")),
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Proposal values are invalid.") from exc
    store.save(identity, deal.model_copy(update={"proposals": (*deal.proposals, proposal)}))
    _sync_prospect(
        request,
        identity,
        prospect_id,
        status=ProspectStatus.proposal,
        next_action="Review and send proposal externally",
    )
    return RedirectResponse(f"/agency/prospects/{prospect_id}/deal", status_code=303)


@router.post("/agency/prospects/{prospect_id}/deal/proposals/{version}/status")
async def update_proposal_status(
    prospect_id: str,
    version: int,
    request: Request,
) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    store = TenantDealStore(_root(request))
    deal = store.load_or_empty(identity, prospect_id)
    values = _values(await request.body())
    try:
        next_status = ProposalStatus(_one(values, "status"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown proposal status.") from exc
    proposals = list(deal.proposals)
    for index, proposal in enumerate(proposals):
        if proposal.version != version:
            continue
        try:
            proposals[index] = ProposalVersion.model_validate(
                {
                    **proposal.model_dump(mode="json"),
                    "status": next_status,
                    "acceptance_reference": _one(values, "acceptance_reference"),
                    "updated_at": datetime.now(UTC),
                }
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail="Accepted proposals require acceptance evidence/reference.",
            ) from exc
        break
    else:
        raise HTTPException(status_code=404, detail="Proposal version not found.")
    store.save(identity, deal.model_copy(update={"proposals": tuple(proposals)}))
    next_action = (
        "Complete agreement and payment gate before work starts"
        if next_status is ProposalStatus.accepted
        else "Continue proposal follow-up"
    )
    _sync_prospect(
        request,
        identity,
        prospect_id,
        status=ProspectStatus.proposal,
        next_action=next_action,
    )
    return RedirectResponse(f"/agency/prospects/{prospect_id}/deal", status_code=303)
