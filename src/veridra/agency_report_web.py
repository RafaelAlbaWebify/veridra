# ruff: noqa: E501
from __future__ import annotations

import html
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .agency_navigation import agency_navigation
from .email_delivery import EmailDeliveryError
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .pdf_reports import PdfRenderError, render_pdf
from .progress import ProgressSummary, build_progress_summary
from .report_delivery import ReportDeliveryStore, send_report_pdf
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile
from .reports import render_report
from .request_security import require_request_identity
from .runtime_config import RuntimeConfig, RuntimeEnvironment
from .tenant_assessment_approval_store import TenantAssessmentApprovalStore
from .tenant_entitlements import (
    record_tenant_reserved_usage,
    release_tenant_usage_reservation,
    require_tenant_feature,
    reserve_tenant_usage,
)
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_profile_store import TenantProfileStore, TenantProfileStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import UsageKind

router = APIRouter(prefix="/agency", tags=["agency-reports"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:920px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.success{border-left-color:#16794a;background:#f0faf5}.danger{border-left-color:#a23333;background:#fff3f3}.actions{display:flex;gap:8px;flex-wrap:wrap}.profile{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.profile div{border:1px solid #e2e5e9;border-radius:8px;padding:12px}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:120px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}@media(max-width:700px){.profile{grid-template-columns:1fr}}
"""


class DeliveryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=4000)


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None

def _production_mode(request: Request) -> bool:
    config = getattr(request.app.state, "veridra_runtime_config", None)
    return (
        isinstance(config, RuntimeConfig)
        and config.environment is RuntimeEnvironment.production
    )


def _usage_policy(request: Request) -> TenantWorkspacePolicy:
    return TenantWorkspacePolicy(_root(request))




def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _profile(
    request: Request,
    identity: RequestIdentity,
    profile_id: str | None,
) -> tuple[ReportProfile, bool]:
    if profile_id is None:
        return DEFAULT_REPORT_PROFILE, True
    if _production_mode(request):
        require_tenant_feature(
            TenantWorkspacePolicy(_root(request)),
            identity,
            "white_label",
        )
    profiles = TenantProfileStore(_root(request))
    try:
        return profiles.load(identity, profiles.ref(identity, profile_id)), False
    except TenantProfileStoreError as exc:
        raise HTTPException(status_code=404, detail="Report source not found.") from exc


def _context(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
) -> tuple[Path | None, Any, list[Any], ReportProfile, bool]:
    root = _root(request)
    projects = TenantProjectStore(root)
    history = TenantHistoryStore(root)
    try:
        project = projects.load(identity, projects.ref(identity, project_id))
        assessments = history.list(identity, project_id)
    except (TenantProjectStoreError, TenantHistoryStoreError) as exc:
        raise HTTPException(status_code=404, detail="Report source not found.") from exc
    profile, is_default = _profile(request, identity, project.profile_id)
    return root, project, assessments, profile, is_default


def _latest_progress(
    root: Path | None,
    identity: RequestIdentity,
    project_id: str,
    assessments: list[Any],
) -> ProgressSummary | None:
    if len(assessments) < 2:
        return None
    history = TenantHistoryStore(root)
    latest, previous = assessments[0], assessments[1]
    before = history.load(identity, history.ref(identity, project_id, previous.id))
    after = history.load(identity, history.ref(identity, project_id, latest.id))
    comparison = history.compare(identity, project_id, previous.id, latest.id)
    return build_progress_summary(before, after, comparison)


def _attempt_store(root: Path | None, tenant_id: str) -> ReportDeliveryStore:
    base = root if root is not None else Path.home() / ".veridra" / "tenants"
    return ReportDeliveryStore(base / tenant_id / "report-deliveries")


@router.get("/projects/{project_id}/reports", response_class=HTMLResponse)
def project_report_hub(
    project_id: str,
    request: Request,
    delivery: str | None = None,
    profile: str | None = None,
) -> str:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_reports)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc

    root, project, assessments, report_profile, is_default = _context(request, identity, project_id)
    latest = assessments[0] if assessments else None
    profile_state = "Default Veridra profile" if is_default else "Saved report profile"
    section_labels = ", ".join(report_profile.section_order)
    cta = (
        f"{report_profile.call_to_action_label} — {report_profile.call_to_action_url}"
        if report_profile.call_to_action_label and report_profile.call_to_action_url
        else "Not configured"
    )
    edit_action = (
        f" <a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/reports/profile/edit'>Edit current saved profile</a>"
        if not is_default
        else ""
    )
    profile_summary = f"""<div class='profile'><div><strong>Profile</strong><br>{html.escape(profile_state)}</div><div><strong>Organisation</strong><br>{html.escape(report_profile.organisation_name)}</div><div><strong>Client</strong><br>{html.escape(report_profile.client_name or project.client_label or 'Not set')}</div><div><strong>Language</strong><br>{html.escape(report_profile.language)}</div><div><strong>Accent colour</strong><br>{html.escape(report_profile.accent_colour)}</div><div><strong>Call to action</strong><br>{html.escape(cta)}</div></div><p><strong>Enabled sections:</strong> {html.escape(section_labels)}</p><p><a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/reports/profile'>Create or change report profile</a>{edit_action}</p>"""

    status = ""
    if delivery == "delivered":
        status = "<p class='notice success'><strong>SMTP accepted the report delivery.</strong> This does not prove inbox placement or opening.</p>"
    elif delivery == "failed":
        status = "<p class='notice danger'><strong>The report delivery attempt failed.</strong> Review the recent attempt details before retrying.</p>"
    elif delivery == "not-configured":
        status = "<p class='notice'><strong>Email delivery is not configured.</strong> Configure the server SMTP environment before retrying.</p>"
    if profile == "created":
        status += "<p class='notice success'><strong>The saved report profile was created and applied to this project.</strong></p>"
    elif profile == "updated":
        status += "<p class='notice success'><strong>The project report profile was updated.</strong></p>"

    if latest is None:
        output = "<p class='notice'>No saved assessment is available. Run or save a saved project assessment before generating or sending a report.</p>"
    else:
        approval = TenantAssessmentApprovalStore(root).load(identity, project_id, latest.id)
        if approval is None:
            findings_url = f"/agency/projects/{html.escape(project_id, quote=True)}/assessments/{html.escape(latest.id, quote=True)}/findings"
            output = f"""<p class='notice danger'><strong>Pending human QA.</strong> Assessment {html.escape(latest.id)} cannot be previewed, exported or delivered to the client until it is explicitly approved.</p><p><a class='button' href='{findings_url}'>Review findings and approve assessment</a></p>"""
        else:
            base = f"/api/tenant/projects/{html.escape(project_id, quote=True)}/assessments/{html.escape(latest.id, quote=True)}"
            smtp_configured = getattr(request.app.state, "veridra_smtp_config", None) is not None
            optional_email = (
                f"<a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/reports/send'>Email PDF via configured SMTP</a>"
                if smtp_configured
                else ""
            )
            output = f"""<p class='notice success'><strong>QA approved for client delivery.</strong><br><strong>Report source:</strong> assessment {html.escape(latest.id)}<br><strong>Generated:</strong> {html.escape(latest.generated_at)}<br><strong>Approved:</strong> {html.escape(approval.approved_at.isoformat())}</p><div class='actions'><a class='button' href='{base}/report'>Preview branded HTML</a><a class='button secondary' href='{base}/report.pdf'>Download PDF</a><a class='button secondary' href='{base}/export'>Download evidence ZIP</a><a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/delivery'>Record external delivery</a>{optional_email}</div><p class='muted'>Normal operator flow: preview, download the approved PDF, deliver it through the approved external Webify channel, then record that delivery evidence. SMTP is optional and appears only when configured.</p>"""

    attempts = _attempt_store(root, identity.tenant_id).list_for_project(project_id)[:10]
    attempt_rows = "".join(
        f"<li><strong>{html.escape(attempt.status.value)}</strong> — {html.escape(attempt.attempted_at.isoformat())} — {html.escape(str(attempt.recipient))} — attempt {attempt.attempt_number}{f' — {html.escape(attempt.error)}' if attempt.error else ''}</li>"
        for _, attempt in attempts
    ) or "<li>No report delivery attempts recorded.</li>"
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects'>Client projects</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project overview</a></p><h1>Reports for {html.escape(project.name)}</h1>{status}<p><strong>Website:</strong> {html.escape(project.target_url)}</p></section><section><h2>Branding and content profile</h2>{profile_summary}</section><section><h2>Report outputs</h2>{output}</section><section><h2>Optional SMTP delivery history</h2><ul>{attempt_rows}</ul><p class='muted'>This section records only VERIDRA SMTP attempts. External/manual delivery evidence belongs in Delivery & closure. SMTP acceptance does not prove receipt or opening.</p></section>"""
    return _page(f"{project.name} reports", body)


@router.get("/projects/{project_id}/reports/send", response_class=HTMLResponse)
def report_delivery_confirmation(project_id: str, request: Request) -> str:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_reports)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    _, project, assessments, profile, _ = _context(request, identity, project_id)
    if not assessments:
        raise HTTPException(status_code=404, detail="Report source not found.")
    if TenantAssessmentApprovalStore(_root(request)).load(
        identity, project_id, assessments[0].id
    ) is None:
        raise HTTPException(
            status_code=409,
            detail="Assessment requires human QA approval before client delivery.",
        )
    client = profile.client_name or project.client_label or project.name
    subject = f"Website assessment report for {client}"
    navigation = agency_navigation(identity, current="projects")
    body = f"""{navigation}<section><p><a href='/agency/projects'>Client projects</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}'>Project overview</a> · <a href='/agency/projects/{html.escape(project_id, quote=True)}/reports'>Report hub</a></p><h1>Email branded PDF report</h1><p class='notice'>The latest saved project assessment will be rendered with the project’s selected report profile and attached as a PDF. No email is sent by opening this page.</p><form method='post' action='/agency/projects/{html.escape(project_id, quote=True)}/reports/send'><label for='recipient'>Recipient</label><input id='recipient' name='recipient' type='email' required><label for='subject'>Subject</label><input id='subject' name='subject' maxlength='200' value='{html.escape(subject, quote=True)}' required><label for='message'>Message</label><textarea id='message' name='message' maxlength='4000'>Please find your website assessment report attached.</textarea><p><button type='submit'>Send PDF report</button> <a class='button secondary' href='/agency/projects/{html.escape(project_id, quote=True)}/reports'>Cancel</a></p></form></section>"""
    return _page("Email PDF report", body)


@router.post("/projects/{project_id}/reports/send")
async def submit_report_delivery(project_id: str, request: Request) -> RedirectResponse:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_reports)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    root, project, assessments, profile, _ = _context(request, identity, project_id)
    if not assessments:
        raise HTTPException(status_code=404, detail="Report source not found.")
    if TenantAssessmentApprovalStore(root).load(
        identity, project_id, assessments[0].id
    ) is None:
        raise HTTPException(
            status_code=409,
            detail="Assessment requires human QA approval before client delivery.",
        )
    body = await request.body()
    try:
        payload = DeliveryInput(
            recipient=_single(body, "recipient"),
            subject=_single(body, "subject"),
            message=_single(body, "message"),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Report delivery input is invalid.") from exc
    latest = assessments[0]
    history = TenantHistoryStore(root)
    try:
        assessment = history.load(
            identity,
            history.ref(identity, project_id, latest.id),
        )
    except TenantHistoryStoreError as exc:
        raise HTTPException(status_code=404, detail="Report source not found.") from exc
    reservation_id = ""
    policy = _usage_policy(request)
    if _production_mode(request):
        reservation_id = reserve_tenant_usage(policy, identity, UsageKind.pdf)
    try:
        document = await run_in_threadpool(
            partial(
                render_pdf,
                render_report(
                    assessment,
                    profile,
                    progress=_latest_progress(root, identity, project_id, assessments),
                ),
                target=str(assessment.target),
            )
        )
    except PdfRenderError as exc:
        if reservation_id:
            release_tenant_usage_reservation(policy, identity, reservation_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if reservation_id:
        record_tenant_reserved_usage(
            policy,
            identity,
            reservation_id,
            UsageKind.pdf,
            related_id=latest.id,
            note="SMTP report PDF",
        )
    try:
        attempt = send_report_pdf(
            project_id=project_id,
            assessment_id=latest.id,
            recipient=str(payload.recipient),
            subject=payload.subject,
            message_text=payload.message,
            pdf_content=document.content,
            filename=document.filename,
            store=_attempt_store(root, identity.tenant_id),
        )
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=503, detail="Report delivery could not be prepared.") from exc
    delivery = "not-configured" if attempt is None else attempt.status.value
    return RedirectResponse(
        f"/agency/projects/{project_id}/reports?{urlencode({'delivery': delivery})}",
        status_code=303,
    )
