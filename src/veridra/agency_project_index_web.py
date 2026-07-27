# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .request_security import require_request_identity
from .tenant_project_store import TenantProjectStore

router = APIRouter(prefix="/agency", tags=["agency-projects"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1100px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.card{border:1px solid #dfe3e8;border-radius:9px;padding:18px}.button{display:inline-block;border-radius:7px;background:#22272d;color:#fff;padding:9px 13px;text-decoration:none}.secondary{background:#59636e}.muted{color:#68707a}.actions{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:760px){.cards{grid-template-columns:1fr}}
"""


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _page(body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Client projects · Veridra</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


@router.get("/projects", response_class=HTMLResponse)
def agency_projects(request: Request) -> str:
    identity = require_request_identity(request)
    entries = TenantProjectStore(_root(request)).list(identity)
    if entries:
        cards = "".join(
            "<article class='card'><p class='muted'>{client}</p><h2>{name}</h2><p><strong>Website:</strong> {target}<br><strong>Crawl:</strong> {crawl}<br><strong>Monitoring:</strong> {monitoring}</p><div class='actions'><a class='button' href='/agency/projects/{identifier}'>Open project</a><a class='button secondary' href='/agency/projects/{identifier}/reports'>Reports</a><a class='button secondary' href='/agency/projects/{identifier}/monitoring'>Monitoring</a></div></article>".format(
                client=html.escape(entry.client_label or "Client not labelled"),
                name=html.escape(entry.name),
                target=html.escape(entry.target_url),
                crawl=html.escape(entry.crawl_profile.value.title()),
                monitoring=html.escape(entry.monitoring_cadence.value.title()),
                identifier=html.escape(entry.id, quote=True),
            )
            for entry in entries
        )
    else:
        cards = "<p class='muted'>No client projects exist yet. Run a quick audit and explicitly convert it after reviewing the result.</p>"
    body = f"""<section><p><a href='/agency'>Agency workspace</a></p><h1>Client projects</h1><p class='muted'>Persistent tenant projects are the authoritative home for saved assessments, branded reports, remediation and monitoring.</p><div class='actions'><a class='button' href='/agency'>Start a quick audit</a></div></section><section><div class='cards'>{cards}</div></section>"""
    return _page(body)
