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

from .agency_navigation import agency_navigation
from .deal_lifecycle import ChangeRequestStatus, ScopeChangeRequest
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .tenant_deal_store import TenantDealStore
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError

router = APIRouter(tags=["agency-change-request"])

_STYLE = """
body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}
main{max-width:980px;margin:36px auto;padding:0 20px}
section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}
label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}
textarea{min-height:90px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.card{border:1px solid #e1e5ea;border-radius:8px;padding:16px;margin:12px 0}.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.muted{color:#68707a}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}@media(max-width:700px){.row{grid-template-columns:1fr}}
"""


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


def _one(body: bytes, name: str) -> str:
    values = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return values.get(name, [""])[0].strip()


def _status_options(current: ChangeRequestStatus) -> str:
    return "".join(
        f"<option value='{item.value}'{' selected' if item is current else ''}>"
        f"{item.value.replace('_', ' ').title()}</option>"
        for item in ChangeRequestStatus
    )


@router.get(
    "/agency/prospects/{prospect_id}/deal/change-requests",
    response_class=HTMLResponse,
)
def change_request_page(prospect_id: str, request: Request) -> str:
    identity = _identity(request)
    root = _root(request)
    try:
        prospect = TenantProspectStore(root).load(
            identity,
            TenantProspectStore.ref(identity, prospect_id),
        )
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc
    deal = TenantDealStore(root).load_or_empty(identity, prospect_id)
    cards: list[str] = []
    for item in reversed(deal.change_requests):
        resulting = (
            f"v{item.resulting_proposal_version}"
            if item.resulting_proposal_version is not None
            else "—"
        )
        cards.append(
            f"<div class='card'><h3>Change #{item.sequence} "
            f"<span class='badge'>{html.escape(item.status.value)}</span></h3>"
            f"<p><strong>Request:</strong> {html.escape(item.summary)}</p>"
            f"<p><strong>Scope impact:</strong> {html.escape(item.scope_impact)}</p>"
            f"<p><strong>Price impact:</strong> {html.escape(item.price_impact or 'Not assessed')}</p>"
            f"<p><strong>Timeline impact:</strong> {html.escape(item.timeline_impact or 'Not assessed')}</p>"
            f"<p><strong>Resulting proposal:</strong> {html.escape(resulting)}</p>"
            f"<form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/deal/change-requests/{item.sequence}/status'>"
            f"<label>Status</label><select name='status'>{_status_options(item.status)}</select>"
            "<label>Decision evidence/reference</label>"
            f"<input name='decision_reference' maxlength='1000' value='{html.escape(item.decision_reference, quote=True)}'>"
            "<label>Resulting proposal version (required when incorporated)</label>"
            f"<input name='resulting_proposal_version' type='number' min='1' value='{resulting if resulting != '—' else ''}'>"
            "<button type='submit'>Update change request</button></form></div>"
        )
    history = "".join(cards) or "<p class='muted'>No scope changes recorded.</p>"
    navigation = agency_navigation(identity, current="deals")
    body = (
        f"{navigation}<section><p><a href='/agency/prospects/{html.escape(prospect_id, quote=True)}/deal'>← Sales workflow</a></p>"
        f"<h1>Scope changes — {html.escape(prospect.business_name)}</h1>"
        "<p class='muted'>Record requested changes separately. Approved changes should become a new proposal version rather than rewriting a proposal already sent or accepted.</p></section>"
        f"<section><h2>New scope change</h2><form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/deal/change-requests'>"
        "<label>Requested change</label><textarea name='summary' required></textarea>"
        "<label>Requested by</label><input name='requested_by' value='customer'>"
        "<label>Scope impact</label><textarea name='scope_impact' required></textarea>"
        "<div class='row'><div><label>Price impact</label><input name='price_impact'></div>"
        "<div><label>Timeline impact</label><input name='timeline_impact'></div></div>"
        "<button type='submit'>Record change request</button></form></section>"
        f"<section><h2>Change history</h2>{history}</section>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Scope changes</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


@router.post("/agency/prospects/{prospect_id}/deal/change-requests")
async def create_change_request(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    root = _root(request)
    try:
        TenantProspectStore(root).load(
            identity,
            TenantProspectStore.ref(identity, prospect_id),
        )
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc
    body = await request.body()
    store = TenantDealStore(root)
    deal = store.load_or_empty(identity, prospect_id)
    try:
        change = ScopeChangeRequest(
            sequence=len(deal.change_requests) + 1,
            summary=_one(body, "summary"),
            requested_by=_one(body, "requested_by") or "customer",
            scope_impact=_one(body, "scope_impact"),
            price_impact=_one(body, "price_impact"),
            timeline_impact=_one(body, "timeline_impact"),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Scope change is incomplete.") from exc
    store.save(
        identity,
        deal.model_copy(
            update={
                "change_requests": (*deal.change_requests, change),
                "next_action": "Review scope, price and timeline impact",
                "updated_at": datetime.now(UTC),
            }
        ),
    )
    return RedirectResponse(
        f"/agency/prospects/{prospect_id}/deal/change-requests",
        status_code=303,
    )


@router.post("/agency/prospects/{prospect_id}/deal/change-requests/{sequence}/status")
async def update_change_request(
    prospect_id: str,
    sequence: int,
    request: Request,
) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    body = await request.body()
    store = TenantDealStore(_root(request))
    deal = store.load_or_empty(identity, prospect_id)
    try:
        next_status = ChangeRequestStatus(_one(body, "status"))
        version_raw = _one(body, "resulting_proposal_version")
        resulting_version = int(version_raw) if version_raw else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Change request status is invalid.") from exc

    changes = list(deal.change_requests)
    for index, change in enumerate(changes):
        if change.sequence != sequence:
            continue
        try:
            changes[index] = ScopeChangeRequest.model_validate(
                {
                    **change.model_dump(mode="json"),
                    "status": next_status,
                    "decision_reference": _one(body, "decision_reference"),
                    "resulting_proposal_version": resulting_version,
                    "updated_at": datetime.now(UTC),
                }
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Approved/declined changes require decision evidence; incorporated "
                    "changes also require the resulting proposal version."
                ),
            ) from exc
        break
    else:
        raise HTTPException(status_code=404, detail="Change request not found.")
    store.save(identity, deal.model_copy(update={"change_requests": tuple(changes)}))
    return RedirectResponse(
        f"/agency/prospects/{prospect_id}/deal/change-requests",
        status_code=303,
    )
