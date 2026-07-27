# ruff: noqa: E501
from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile
from .request_security import require_request_identity
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_profile_store import TenantProfileStore, TenantProfileStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/agency", tags=["agency-reports"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:920px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button{display:inline-block;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.actions{display:flex;gap:8px;flex-wrap:wrap}.profile{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.profile div{border:1px solid #e2e5e9;border-radius:8px;padding:12px}@media(max-width:700px){.profile{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _profile(
    request: Request,
    identity: RequestIdentity,
    profile_id: str | None,
) -> tuple[ReportProfile, bool]:
    if profile_id is None:
        return DEFAULT_REPORT_PROFILE, True
    profiles = TenantProfileStore(_root(request))
    try:
        return profiles.load(identity, profiles.ref(identity, profile_id)), False
    except TenantProfileStoreError as exc:
        raise HTTPException(status_code=404, detail="Report source not found.") from exc


@router.get("/projects/{project_id}/reports", response_class=HTMLResponse)
def project_report_hub(project_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_reports)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc

    root = _root(request)
    projects = TenantProjectStore(root)
    history = TenantHistoryStore(root)
    try:
        project = projects.load(identity, projects.ref(identity, project_id))
        assessments = history.list(identity, project_id)
    except (TenantProjectStoreError, TenantHistoryStoreError) as exc:
        raise HTTPException(status_code=404, detail="Report source not found.") from exc

    profile, is_default = _profile(request, identity, project.profile_id)
    latest = assessments[0] if assessments else None
    profile_state = "Default Veridra profile" if is_default else "Tenant report profile"
    section_labels = ", ".join(profile.section_order)
    cta = (
        f"{profile.call_to_action_label} — {profile.call_to_action_url}"
        if profile.call_to_action_label and profile.call_to_action_url
        else "Not configured"
    )
    profile_summary = f"""<div class='profile'><div><strong>Profile</strong><br>{html.escape(profile_state)}</div><div><strong>Organisation</strong><br>{html.escape(profile.organisation_name)}</div><div><strong>Client</strong><br>{html.escape(profile.client_name or project.client_label or 'Not set')}</div><div><strong>Language</strong><br>{html.escape(profile.language)}</div><div><strong>Accent colour</strong><br>{html.escape(profile.accent_colour)}</div><div><strong>Call to action</strong><br>{html.escape(cta)}</div></div><p><strong>Enabled sections:</strong> {html.escape(section_labels)}</p>"""

    if latest is None:
        output = "<p class='notice'>No saved assessment is available. Run or save a tenant-qualified assessment before generating a report.</p>"
    else:
        base = f"/api/tenant/projects/{html.escape(project_id, quote=True)}/assessments/{html.escape(latest.id, quote=True)}"
        output = f"""<p class='notice'><strong>Report source:</strong> assessment {html.escape(latest.id)}<br><strong>Generated:</strong> {html.escape(latest.generated_at)}</p><div class='actions'><a class='button' href='{base}/report'>Preview branded HTML</a><a class='button secondary' href='{base}/report.pdf'>Download PDF</a><a class='button secondary' href='{base}/export'>Download evidence ZIP</a></div><p class='muted'>These actions use the saved tenant assessment and the project’s selected report profile. Opening this hub does not generate or persist new assessment data.</p>"""

    body = f"""<section><p><a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project</a> · <a href='/agency'>Agency workflow</a></p><h1>Reports for {html.escape(project.name)}</h1><p><strong>Website:</strong> {html.escape(project.target_url)}</p></section><section><h2>Branding and content profile</h2>{profile_summary}</section><section><h2>Report outputs</h2>{output}</section>"""
    return _page(f"{project.name} reports", body)
