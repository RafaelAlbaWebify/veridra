from __future__ import annotations

import html
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .request_security import require_request_identity
from .tenant_deal_store import TenantDealStore
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError

router = APIRouter(tags=["agency-proposal-artifact"])

_STYLE = """
body{margin:0;background:#f5f6f8;color:#17191c;font:15px Arial,sans-serif}
main{max-width:860px;margin:36px auto;background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:40px}
h1,h2{margin-top:0}section{margin:28px 0}.meta{display:grid;grid-template-columns:1fr 1fr;gap:12px}.box{border:1px solid #e1e5ea;border-radius:8px;padding:16px}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.price{font-size:24px;font-weight:700}@media(max-width:700px){main{margin:0;border:0;border-radius:0}.meta{grid-template-columns:1fr}}
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


def _proposal_html(prospect_id: str, version: int, request: Request) -> tuple[str, str]:
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
    proposal = next((item for item in deal.proposals if item.version == version), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal version not found.")

    recurring = (
        f"<p><strong>Recurring service:</strong> {html.escape(proposal.currency)} "
        f"{proposal.recurring_amount:.2f} {html.escape(proposal.recurring_cadence)}</p>"
        if proposal.recurring_amount is not None
        else ""
    )
    acceptance = (
        "<section><h2>Acceptance record</h2>"
        f"<p>{html.escape(proposal.acceptance_reference)}</p></section>"
        if proposal.acceptance_reference
        else ""
    )
    body = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(proposal.title)}</title><style>{_STYLE}</style></head><body><main>"
        "<p class='muted'>Webify Digital Solutions · Proposal / quote</p>"
        f"<h1>{html.escape(proposal.title)}</h1>"
        f"<p><strong>Client:</strong> {html.escape(prospect.business_name)}</p>"
        "<div class='meta'>"
        f"<div class='box'><strong>Version</strong><br>v{proposal.version}</div>"
        f"<div class='box'><strong>Status</strong><br>{html.escape(proposal.status.value.title())}</div>"
        f"<div class='box'><strong>Valid until</strong><br>{proposal.valid_until.isoformat()}</div>"
        f"<div class='box'><strong>Timeline</strong><br>{html.escape(proposal.timeline)}</div>"
        "</div>"
        "<section><h2>Scope</h2>"
        f"<p>{html.escape(proposal.scope)}</p></section>"
        "<section><h2>Deliverables</h2>"
        f"<p>{html.escape(proposal.deliverables)}</p></section>"
        "<section><h2>Exclusions</h2>"
        f"<p>{html.escape(proposal.exclusions or 'None recorded')}</p></section>"
        "<section><h2>Assumptions</h2>"
        f"<p>{html.escape(proposal.assumptions or 'None recorded')}</p></section>"
        "<section><h2>Commercial terms</h2>"
        f"<p class='price'>{html.escape(proposal.currency)} {proposal.price_amount:.2f}</p>"
        f"{recurring}</section>{acceptance}"
        "<p class='notice'>This proposal records scope and commercial intent. It is not an "
        "accounting invoice, payment receipt, or e-signature record. Agreement and payment "
        "evidence are handled by the next business-cycle gate.</p>"
        "</main></body></html>"
    )
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", prospect.business_name).strip("-") or "client"
    return body, f"{slug}-proposal-v{proposal.version}.html"


@router.get(
    "/agency/prospects/{prospect_id}/deal/proposals/{version}/artifact",
    response_class=HTMLResponse,
)
def proposal_preview(prospect_id: str, version: int, request: Request) -> str:
    body, _ = _proposal_html(prospect_id, version, request)
    return body


@router.get("/agency/prospects/{prospect_id}/deal/proposals/{version}/download")
def proposal_download(prospect_id: str, version: int, request: Request) -> Response:
    body, filename = _proposal_html(prospect_id, version, request)
    return Response(
        content=body.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
