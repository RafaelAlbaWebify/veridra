# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .agency_navigation import agency_navigation
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .request_security import require_request_identity
from .tenant_deal_store import TenantDealStore
from .tenant_prospect_store import TenantProspectStore

router = APIRouter(tags=["agency-deal-index"])

_STYLE = """
*{box-sizing:border-box}
body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}
main{max-width:1180px;margin:36px auto;padding:0 20px}
section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}
.button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:9px 12px;text-decoration:none}
.secondary{background:#59636e}
.muted{color:#68707a}
.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}
.actions{display:flex;gap:6px;flex-wrap:wrap}
table{width:100%;border-collapse:collapse}
th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}
.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}
.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}
@media(max-width:760px){table{display:block;overflow:auto}}
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


@router.get("/agency/deals", response_class=HTMLResponse)
def deal_index(request: Request) -> str:
    identity = _identity(request)
    root = _root(request)
    prospects = TenantProspectStore(root).list(identity)
    deal_store = TenantDealStore(root)
    rows: list[str] = []
    for prospect_id, prospect in prospects:
        deal = deal_store.load_or_empty(identity, prospect_id)
        reply = (
            deal.reply_outcome.value.replace("_", " ")
            if deal.reply_outcome
            else "Not recorded"
        )
        discovery = "Ready" if deal.discovery is not None else "Not captured"
        latest = deal.latest_proposal
        proposal = (
            f"v{latest.version} · {latest.status.value}"
            if latest is not None
            else "No proposal"
        )
        business = html.escape(prospect.business_name)
        prospect_status = html.escape(prospect.status.value)
        next_action = html.escape(prospect.next_action or deal.next_action or "—")
        escaped_id = html.escape(prospect_id, quote=True)
        deal_url = f"/agency/prospects/{escaped_id}/deal"
        changes_url = f"/agency/prospects/{escaped_id}/deal/change-requests"
        artifact_action = ""
        if latest is not None:
            artifact_url = (
                f"/agency/prospects/{escaped_id}/deal/proposals/"
                f"{latest.version}/artifact"
            )
            artifact_action = (
                f"<a class='button secondary' href='{artifact_url}'>Preview proposal</a>"
            )
        change_label = (
            f"Scope changes ({len(deal.change_requests)})"
            if deal.change_requests
            else "Scope changes"
        )
        rows.append(
            "<tr>"
            f"<td><strong>{business}</strong><br>"
            f"<span class='muted'>{prospect_status}</span></td>"
            f"<td>{html.escape(reply.title())}</td>"
            f"<td>{html.escape(discovery)}</td>"
            f"<td><span class='badge'>{html.escape(proposal)}</span></td>"
            f"<td>{next_action}</td>"
            "<td><div class='actions'>"
            f"<a class='button' href='{deal_url}'>Open sales workflow</a>"
            f"{artifact_action}"
            f"<a class='button secondary' href='{changes_url}'>{change_label}</a>"
            "</div></td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr>"
        "<th>Prospect</th><th>Reply</th><th>Discovery</th>"
        "<th>Proposal</th><th>Next action</th><th></th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else "<p class='muted'>No prospects yet. Create or discover a prospect first.</p>"
    )
    navigation = agency_navigation(identity, current="deals")
    body = (
        f"{navigation}<section><h1>Sales / proposals</h1>"
        "<p class='muted'>Move real replies through discovery and a bounded, "
        "versioned proposal before agreement/payment. This records the sales process; "
        "VERIDRA is not the email inbox or signature provider.</p>"
        f"{table}</section>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Sales / proposals</title><style>{_STYLE}</style>"
        f"</head><body><main>{body}</main></body></html>"
    )
