# ruff: noqa: E501
from __future__ import annotations

import html
import os
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .agency_navigation import agency_navigation
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .leadmap_import import LeadMapImportError, prospects_from_leadmap_export
from .prospect_ingest import DiscoveryIngestAction, TenantProspectDiscoveryIngestor
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy

router = APIRouter(prefix="/agency/prospects", tags=["agency-prospect-import"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:900px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}textarea{width:100%;min-height:320px;padding:10px;border:1px solid #cfd4da;border-radius:7px;font-family:monospace}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}
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
        raise HTTPException(status_code=503, detail="Prospect import is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Prospect import request is not permitted.") from exc


def _payload(body: bytes) -> str:
    values = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return values.get("payload", [""])[0].strip()


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request) -> str:
    identity = _identity(request)
    navigation = agency_navigation(identity, current="leads-import")
    body = f"{navigation}<section><p><a href='/agency/prospects'>← Prospects</a></p><h1>Import existing LEADS records</h1><p class='muted'>Paste a LEADS schema 1.1 JSON export. Veridra validates the complete payload before ingest. Existing prospects are enriched safely; their human qualification, rejection, contact, audit and outreach state is preserved.</p><form method='post' action='/agency/prospects/import'><label for='payload'><strong>LEADS JSON export</strong></label><textarea id='payload' name='payload' required></textarea><p><button type='submit'>Validate and import</button></p></form></section>"
    return _page("Import LEADS prospects", body)


@router.post("/import", response_class=HTMLResponse)
async def import_submit(request: Request) -> HTMLResponse:
    identity = _identity(request)
    _trusted_origin(request)
    payload = _payload(await request.body())
    if not payload:
        return HTMLResponse(
            _page(
                "Import LEADS prospects",
                "<section><h1>Nothing to import</h1><p class='muted'>Paste a LEADS schema 1.1 JSON export.</p><p><a href='/agency/prospects/import'>Return to import</a></p></section>",
            ),
            status_code=400,
        )
    try:
        prospects = prospects_from_leadmap_export(payload)
        outcomes = TenantProspectDiscoveryIngestor(_root(request)).ingest(identity, prospects)
    except (LeadMapImportError, ValueError) as exc:
        return HTMLResponse(
            _page(
                "Import failed",
                f"<section><h1>LEADS export was not imported</h1><p class='muted'>{html.escape(str(exc))}</p><p><a href='/agency/prospects/import'>Return to import</a></p></section>",
            ),
            status_code=400,
        )

    counts = {action: 0 for action in DiscoveryIngestAction}
    for outcome in outcomes:
        counts[outcome.action] += 1
    body = (
        "<section><h1>LEADS import complete</h1>"
        f"<p><strong>{len(outcomes)}</strong> records processed: "
        f"{counts[DiscoveryIngestAction.created]} created, "
        f"{counts[DiscoveryIngestAction.enriched]} safely enriched, "
        f"{counts[DiscoveryIngestAction.unchanged]} unchanged.</p>"
        "<p class='notice'>Existing human workflow state was preserved by the prospect ingest policy.</p>"
        "<p><a class='button' href='/agency/prospects'>Open prospects</a></p></section>"
    )
    return HTMLResponse(_page("LEADS import complete", body))
