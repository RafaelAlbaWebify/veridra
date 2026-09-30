from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from .customer_store import (
    CustomerBillingState,
    CustomerBillingStatus,
    CustomerRecord,
    CustomerSourceType,
)
from .deal_lifecycle import ProposalStatus, ProposalVersion
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .prospect import Prospect, ProspectStatus
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .tenant_customer_store import TenantCustomerStore, TenantCustomerStoreError
from .tenant_deal_store import TenantDealStore
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError

router = APIRouter(tags=["agency-proposal-transition"])

_ALLOWED_TRANSITIONS: dict[ProposalStatus, frozenset[ProposalStatus]] = {
    ProposalStatus.draft: frozenset({ProposalStatus.draft, ProposalStatus.sent}),
    ProposalStatus.sent: frozenset(
        {
            ProposalStatus.sent,
            ProposalStatus.accepted,
            ProposalStatus.declined,
            ProposalStatus.expired,
        }
    ),
    ProposalStatus.accepted: frozenset({ProposalStatus.accepted}),
    ProposalStatus.declined: frozenset({ProposalStatus.declined}),
    ProposalStatus.expired: frozenset({ProposalStatus.expired}),
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


def _ensure_customer_on_acceptance(
    request: Request,
    identity: RequestIdentity,
    prospect_id: str,
    proposal: ProposalVersion,
) -> None:
    prospect_store = TenantProspectStore(_root(request))
    try:
        prospect = prospect_store.load(
            identity,
            prospect_store.ref(identity, prospect_id),
        )
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc

    customer = CustomerRecord(
        business_name=prospect.business_name,
        contact_name=prospect.contact_name,
        contact_email=prospect.contact_email or "",
        phone=prospect.phone or "",
        website=prospect.website,
        source_type=CustomerSourceType.prospect,
        source_id=prospect_id,
        offer_service=proposal.title,
        quoted_value=Decimal(str(proposal.price_amount)),
        currency=proposal.currency,
        commercial_notes=(
            f"Accepted proposal v{proposal.version}: "
            f"{proposal.acceptance_reference}"
        ),
        billing=CustomerBillingState(
            status=CustomerBillingStatus.reference_pending,
            invoice_amount=Decimal(str(proposal.price_amount)),
            currency=proposal.currency,
            deposit_required=True,
            deposit_amount=Decimal(str(proposal.price_amount)),
        ),
        booking_gate_required=True,
    )
    try:
        TenantCustomerStore(_root(request)).upsert_from_prospect_conversion(
            identity,
            customer,
        )
    except TenantCustomerStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail="Accepted proposal could not create customer onboarding.",
        ) from exc


def _sync_next_action(
    request: Request,
    identity: RequestIdentity,
    prospect_id: str,
    next_action: str,
    *,
    accepted_proposal: ProposalVersion | None = None,
) -> None:
    store = TenantProspectStore(_root(request))
    try:
        prospect = store.load(identity, store.ref(identity, prospect_id))
        updates: dict[str, object] = {
            "status": (
                ProspectStatus.customer
                if accepted_proposal is not None
                else ProspectStatus.proposal
            ),
            "next_action": next_action,
            "updated_at": datetime.now(UTC),
        }
        if accepted_proposal is not None:
            updates.update(
                {
                    "outreach_offer": accepted_proposal.title,
                    "quoted_value": accepted_proposal.price_amount,
                    "currency": accepted_proposal.currency,
                }
            )
        updated = Prospect.model_validate(
            {**prospect.model_dump(mode="json"), **updates}
        )
        store.replace(identity, store.ref(identity, prospect_id), updated)
    except TenantProspectStoreError as exc:
        raise HTTPException(
            status_code=409,
            detail="Prospect stage could not be synchronized.",
        ) from exc


@router.post("/agency/prospects/{prospect_id}/deal/proposals/{version}/status")
async def update_proposal_status_strict(
    prospect_id: str,
    version: int,
    request: Request,
) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    body = await request.body()
    try:
        next_status = ProposalStatus(_one(body, "status"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown proposal status.") from exc

    store = TenantDealStore(_root(request))
    deal = store.load_or_empty(identity, prospect_id)
    proposals = list(deal.proposals)
    for index, proposal in enumerate(proposals):
        if proposal.version != version:
            continue
        if next_status not in _ALLOWED_TRANSITIONS[proposal.status]:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Proposal v{version} cannot move from {proposal.status.value} "
                    f"to {next_status.value}. Create a new proposal version for changed scope."
                ),
            )
        acceptance_reference = _one(body, "acceptance_reference")
        if proposal.status is ProposalStatus.accepted:
            acceptance_reference = proposal.acceptance_reference
        if next_status is ProposalStatus.accepted and proposal.valid_until < date.today():
            raise HTTPException(
                status_code=409,
                detail="Expired proposal validity cannot be accepted; create a new version.",
            )
        try:
            proposals[index] = ProposalVersion.model_validate(
                {
                    **proposal.model_dump(mode="json"),
                    "status": next_status,
                    "acceptance_reference": acceptance_reference,
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
    if next_status is ProposalStatus.accepted:
        _ensure_customer_on_acceptance(
            request,
            identity,
            prospect_id,
            proposals[index],
        )
    next_action = {
        ProposalStatus.draft: "Review proposal before sending externally",
        ProposalStatus.sent: "Follow up on proposal before validity expires",
        ProposalStatus.accepted: "Complete agreement and payment gate before work starts",
        ProposalStatus.declined: "Record loss reason or create a new scoped version if requested",
        ProposalStatus.expired: "Create a new proposal version if the opportunity remains active",
    }[next_status]
    _sync_next_action(
        request,
        identity,
        prospect_id,
        next_action,
        accepted_proposal=(
            proposals[index] if next_status is ProposalStatus.accepted else None
        ),
    )
    return RedirectResponse(f"/agency/prospects/{prospect_id}/deal", status_code=303)
