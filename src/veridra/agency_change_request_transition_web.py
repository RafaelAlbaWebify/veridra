from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

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

router = APIRouter(tags=["agency-change-request-transition"])

_ALLOWED: dict[ChangeRequestStatus, frozenset[ChangeRequestStatus]] = {
    ChangeRequestStatus.requested: frozenset(
        {
            ChangeRequestStatus.requested,
            ChangeRequestStatus.reviewing,
            ChangeRequestStatus.approved,
            ChangeRequestStatus.declined,
        }
    ),
    ChangeRequestStatus.reviewing: frozenset(
        {
            ChangeRequestStatus.reviewing,
            ChangeRequestStatus.approved,
            ChangeRequestStatus.declined,
        }
    ),
    ChangeRequestStatus.approved: frozenset(
        {ChangeRequestStatus.approved, ChangeRequestStatus.incorporated}
    ),
    ChangeRequestStatus.declined: frozenset({ChangeRequestStatus.declined}),
    ChangeRequestStatus.incorporated: frozenset({ChangeRequestStatus.incorporated}),
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


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


@router.post("/agency/prospects/{prospect_id}/deal/change-requests/{sequence}/status")
async def update_change_request_strict(
    prospect_id: str,
    sequence: int,
    request: Request,
) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    try:
        next_status = ChangeRequestStatus(_one(values, "status"))
        version_raw = _one(values, "resulting_proposal_version")
        resulting_version = int(version_raw) if version_raw else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Change request status is invalid.") from exc

    store = TenantDealStore(_root(request))
    deal = store.load_or_empty(identity, prospect_id)
    changes = list(deal.change_requests)
    for index, change in enumerate(changes):
        if change.sequence != sequence:
            continue
        if next_status not in _ALLOWED[change.status]:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Change #{sequence} cannot move from {change.status.value} "
                    f"to {next_status.value}."
                ),
            )
        if next_status is ChangeRequestStatus.incorporated:
            if resulting_version is None:
                raise HTTPException(
                    status_code=400,
                    detail="Incorporated changes require the resulting proposal version.",
                )
            if not any(item.version == resulting_version for item in deal.proposals):
                raise HTTPException(
                    status_code=409,
                    detail="Resulting proposal version does not exist in this deal.",
                )
        decision_reference = _one(values, "decision_reference")
        if change.status in {
            ChangeRequestStatus.approved,
            ChangeRequestStatus.declined,
        }:
            decision_reference = change.decision_reference
        try:
            changes[index] = ScopeChangeRequest.model_validate(
                {
                    **change.model_dump(mode="json"),
                    "status": next_status,
                    "decision_reference": decision_reference,
                    "resulting_proposal_version": resulting_version,
                    "updated_at": datetime.now(UTC),
                }
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail="Approved or declined changes require decision evidence.",
            ) from exc
        break
    else:
        raise HTTPException(status_code=404, detail="Change request not found.")

    store.save(identity, deal.model_copy(update={"change_requests": tuple(changes)}))
    return RedirectResponse(
        f"/agency/prospects/{prospect_id}/deal/change-requests",
        status_code=303,
    )
