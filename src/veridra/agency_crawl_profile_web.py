# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .agency_navigation import agency_navigation
from .crawl_profiles import CrawlProfileName, resolve_crawl_profile
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .project_store import ClientProject
from .request_security import require_request_identity
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency", tags=["agency-crawl-profile"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:920px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}label{display:block;font-weight:700;margin:12px 0 5px}select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.actions{display:flex;gap:8px;flex-wrap:wrap}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}
"""


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _load(request: Request, identity: RequestIdentity, project_id: str) -> tuple[TenantProjectStore, ClientProject]:
    store = TenantProjectStore(_root(request))
    try:
        return store, store.load(identity, store.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


def _can_manage(identity: RequestIdentity) -> bool:
    try:
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError:
        return False
    return True


def _options(selected: CrawlProfileName) -> str:
    labels = {
        CrawlProfileName.quick: "Quick — up to 10 pages, depth 1",
        CrawlProfileName.standard: "Standard — up to 25 pages, depth 2",
        CrawlProfileName.deep: "Deep — up to 100 pages, depth 3",
    }
    return "".join(
        "<option value='{value}'{selected}>{label}</option>".format(
            value=profile.value,
            selected=" selected" if profile == selected else "",
            label=html.escape(label),
        )
        for profile, label in labels.items()
    )


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


@router.get("/projects/{project_id}/crawl-profile", response_class=HTMLResponse)
def project_crawl_profile(project_id: str, request: Request, saved: bool = False) -> str:
    identity = require_request_identity(request)
    _, project = _load(request, identity, project_id)
    active = project.resolved_crawl_profile()
    limits = active.limits
    status = "<p class='notice'><strong>Crawl profile saved.</strong> Future project assessments and monitoring runs will use these limits.</p>" if saved else ""
    if _can_manage(identity):
        form = f"<form method='post' action='/agency/projects/{html.escape(project_id, quote=True)}/crawl-profile'><label for='crawl_profile'>Named crawl profile</label><select id='crawl_profile' name='crawl_profile'>{_options(project.crawl_profile)}</select><p class='muted'>Only server-defined profiles are available here. Deep remains capped at 100 pages and depth 3.</p><button type='submit'>Save crawl profile</button></form>"
    else:
        form = "<p class='notice'>Your current workspace role can inspect this profile but cannot change it.</p>"
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects'>Client projects</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project overview</a></p><h1>Crawl profile for {html.escape(project.name)}</h1>{status}<p><strong>Current profile:</strong> {html.escape(active.name.value.title())}<br><strong>Effective pages:</strong> {limits.max_pages}<br><strong>Effective depth:</strong> {limits.max_depth}<br><strong>Total byte ceiling:</strong> {limits.max_total_bytes}<br><strong>Per-page byte ceiling:</strong> {limits.per_page_bytes}<br><strong>Timeout:</strong> {limits.timeout:g} seconds<br><strong>Sitemap files:</strong> {limits.max_sitemaps}<br><strong>Sitemap URLs:</strong> {limits.max_sitemap_urls}</p></section><section><h2>Future assessment depth</h2>{form}</section>"""
    return _page(f"{project.name} crawl profile", body)


@router.post("/projects/{project_id}/crawl-profile")
async def save_project_crawl_profile(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_projects)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    store, project = _load(request, identity, project_id)
    body = await request.body()
    try:
        selected = CrawlProfileName(_single(body, "crawl_profile"))
        if selected == CrawlProfileName.custom:
            raise ValueError("Custom crawl values are not available in this workflow.")
        resolve_crawl_profile(selected)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Crawl profile is invalid.") from exc
    replacement = ClientProject.model_validate(
        project.model_copy(
            update={
                "crawl_profile": selected,
                "crawl_max_pages": None,
                "crawl_max_depth": None,
                "crawl_max_total_bytes": None,
                "crawl_per_page_bytes": None,
                "crawl_timeout": None,
                "crawl_max_sitemaps": None,
                "crawl_max_sitemap_urls": None,
            }
        )
    )
    try:
        store.replace(identity, store.ref(identity, project_id), replacement)
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc
    return RedirectResponse(
        f"/agency/projects/{project_id}/crawl-profile?{urlencode({'saved': 'true'})}",
        status_code=303,
    )
