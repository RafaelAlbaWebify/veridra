from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from .deal_lifecycle import ReplyOutcome
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

router = APIRouter(tags=["agency-reply-transition"])

_NEXT_ACTIONS = {
    ReplyOutcome.positive: "Complete discovery before preparing a scoped proposal",
    ReplyOutcome.negative: "Record the explicit commercial loss reason and close the opportunity",
    ReplyOutcome.price_request: "Confirm minimum scope and requirements before quoting a price",
    ReplyOutcome.call_request: "Schedule and complete the discovery call",
    ReplyOutcome.different_scope: "Capture the requested scope and assess fit before quoting",
    ReplyOutcome.no_response: "Set a bounded follow-up date or close as no response",
}


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
        raise HTTPException(
            status_code=403,
            detail="Sales workflow request is not permitted.",
        ) from exc


def _one(body: bytes, name: str) -> str:
    values = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return values.get(name, [""])[0].strip()


@router.post("/agency/prospects/{prospect_id}/deal/reply")
async def save_reply_with_next_action(
    prospect_id: str,
    request: Request,
) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    root = _root(request)
    prospect_store = TenantProspectStore(root)
    try:
        prospect = prospect_store.load(
            identity,
            prospect_store.ref(identity, prospect_id),
        )
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc

    body = await request.body()
    outcome_raw = _one(body, "reply_outcome")
    if not outcome_raw:
        raise HTTPException(
            status_code=400,
            detail="Choose the observed reply outcome before saving.",
        )
    try:
        outcome = ReplyOutcome(outcome_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown reply outcome.") from exc

    explicit_next_action = _one(body, "next_action")
    next_action = explicit_next_action or _NEXT_ACTIONS[outcome]
    deal_store = TenantDealStore(root)
    deal = deal_store.load_or_empty(identity, prospect_id).model_copy(
        update={
            "reply_outcome": outcome,
            "conversation_summary": _one(body, "conversation_summary"),
            "next_action": next_action,
            "updated_at": datetime.now(UTC),
        }
    )
    try:
        deal_store.save(identity, deal)
    except TenantDealStoreError as exc:
        raise HTTPException(status_code=500, detail="Reply context could not be saved.") from exc

    prospect_status = (
        ProspectStatus.conversation
        if outcome in {ReplyOutcome.call_request, ReplyOutcome.different_scope}
        else ProspectStatus.responded
    )
    updated = Prospect.model_validate(
        {
            **prospect.model_dump(mode="json"),
            "status": prospect_status,
            "next_action": next_action,
            "updated_at": datetime.now(UTC),
        }
    )
    try:
        prospect_store.replace(identity, prospect_store.ref(identity, prospect_id), updated)
    except TenantProspectStoreError as exc:
        raise HTTPException(
            status_code=409,
            detail="Prospect reply state could not be synchronized.",
        ) from exc
    return RedirectResponse(f"/agency/prospects/{prospect_id}/deal", status_code=303)
