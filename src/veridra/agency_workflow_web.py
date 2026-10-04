# ruff: noqa: E501
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .agency_navigation import agency_navigation
from .identity_tenancy import RequestIdentity
from .request_security import require_request_identity
from .runtime_config import RuntimeConfig, RuntimeEnvironment, local_agency_mode_enabled
from .tenant_project_store import TenantProjectStore
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import (
    PLAN_CATALOGUE,
    UsageKind,
    WorkspaceStatus,
    quota_decision,
)

router = APIRouter(tags=["agency-workflow"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;font:14px Arial,sans-serif;background:#f7f8fa;color:#17191c}
main{max-width:1240px;margin:0 auto;padding:36px 22px}.top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:22px}
.eyebrow{font-size:12px;text-transform:uppercase;color:#68707a}.muted{color:#68707a}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
section,.card{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:22px}.steps{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:18px 0}
.step{background:#fff;border:1px solid #dfe3e8;border-radius:8px;padding:14px}.step strong{display:block;margin-bottom:6px}.actions{display:flex;gap:8px;flex-wrap:wrap}
.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}
input{width:100%;padding:11px;border:1px solid #cfd4da;border-radius:7px;margin:6px 0 10px}.links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:12px}
.links a{display:block;border:1px solid #dfe3e8;border-radius:7px;padding:12px;text-decoration:none;color:#22272d;background:#fff}.notice{border-left:4px solid #68707a;padding:12px 14px;background:#f4f6f8}
@media(max-width:900px){.steps{grid-template-columns:1fr 1fr}.links{grid-template-columns:1fr 1fr}}
@media(max-width:680px){.top,.grid{display:block}.card,section{margin-bottom:14px}.steps,.links{grid-template-columns:1fr}}
"""


def _operator_mode() -> bool:
    return os.environ.get("VERIDRA_ENV", "").strip().lower() == "operator"


def _local_agency_mode() -> bool:
    return local_agency_mode_enabled()


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _hosted_plan_state(
    request: Request,
    identity: RequestIdentity,
) -> tuple[bool, bool, bool, bool, bool]:
    config = getattr(request.app.state, "veridra_runtime_config", None)
    if not (
        isinstance(config, RuntimeConfig)
        and config.environment is RuntimeEnvironment.production
    ):
        return True, True, True, True, True
    policy = TenantWorkspacePolicy(_root(request))
    workspace = policy.load(identity)
    if workspace.status is not WorkspaceStatus.active:
        return False, False, False, False, False
    entitlement = PLAN_CATALOGUE[workspace.plan]
    audit_allowed = quota_decision(
        workspace,
        policy.usage_ledger(identity),
        UsageKind.audit,
    ).allowed
    project_capacity = (
        len(TenantProjectStore(_root(request)).list(identity))
        < entitlement.max_projects
    )
    return (
        entitlement.white_label,
        entitlement.embedded_lead_forms,
        entitlement.monthly_monitoring_runs > 0,
        audit_allowed,
        project_capacity,
    )


def _page(body: str, *, title: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


@router.get("/agency", response_class=HTMLResponse)
def agency_workflow_home(request: Request) -> str:
    identity = require_request_identity(request)
    if _local_agency_mode():
        body = f"""
        {agency_navigation(identity, current="home")}
        <div class='top'><div><p class='eyebrow'>WEBIFY · VERIDRA LOCAL</p><h1>Run Webify sales, website audits and client delivery from one place</h1>
        <p class='muted'>This is Webify's private local workspace. There is no VERIDRA subscription, SaaS plan or separate agency signup in this mode.</p></div>
        <div class='actions'><a class='button' href='/agency/prospects/discover'>Find prospects</a><a class='button secondary' href='/agency/projects'>Open client projects</a></div></div>
        <div class='steps'>
          <div class='step'><strong>1. Find</strong><span class='muted'>Discover or receive a business opportunity.</span></div>
          <div class='step'><strong>2. Qualify</strong><span class='muted'>Decide whether the opportunity is worth pursuing.</span></div>
          <div class='step'><strong>3. Audit</strong><span class='muted'>Collect bounded website evidence.</span></div>
          <div class='step'><strong>4. Deliver</strong><span class='muted'>Turn accepted work into projects, reports and remediation.</span></div>
          <div class='step'><strong>5. Prove</strong><span class='muted'>Monitor and re-audit improvements over time.</span></div>
        </div>
        <div class='grid'>
          <section><p class='eyebrow'>Outbound / research</p><h2>Find and qualify prospects</h2>
          <p>Discover businesses, review observed opportunities and keep worthwhile candidates in Webify's prospect and sales pipeline.</p>
          <div class='actions'><a class='button' href='/agency/prospects/discover'>Find prospects</a><a class='button secondary' href='/agency/prospects'>Prospect pipeline</a></div></section>
          <section><p class='eyebrow'>Direct website review</p><h2>Run an audit</h2>
          <p class='muted'>Use this when you already know the website you want to inspect. A completed audit can be converted into a persistent client project.</p>
          <form method='get' action='/agency/quick-audit'><label for='target'><strong>Public website</strong></label>
          <input id='target' name='target' maxlength='2048' placeholder='example.com' required>
          <button type='submit'>Run website audit</button></form></section>
          <section><p class='eyebrow'>Inbound</p><h2>Leads and audit forms</h2>
          <p>Review inbound audit leads or configure Webify-branded lead forms without any VERIDRA plan gate.</p>
          <div class='actions'><a class='button' href='/agency/leads'>Inbound leads</a><a class='button secondary' href='/agency/lead-forms'>Lead forms</a></div></section>
          <section><p class='eyebrow'>Delivery</p><h2>Client work</h2>
          <p>Manage accepted customers, projects, branded reports, remediation tasks, monitoring and recurring Presence Care.</p>
          <div class='actions'><a class='button' href='/agency/customers'>Customers</a><a class='button secondary' href='/agency/projects'>Client projects</a></div></section>
        </div>
        <section><h2>Webify operating areas</h2><div class='links'>
          <a href='/agency/prospects'><strong>Prospects</strong><br><span class='muted'>Research and qualification before outreach.</span></a>
          <a href='/agency/deals'><strong>Sales / proposals</strong><br><span class='muted'>Commercial conversations, proposals and progression.</span></a>
          <a href='/agency/leads'><strong>Inbound leads</strong><br><span class='muted'>Audit-form leads and follow-up.</span></a>
          <a href='/agency/lead-forms'><strong>Lead forms</strong><br><span class='muted'>Webify-branded embedded audit capture.</span></a>
          <a href='/agency/customers'><strong>Customers</strong><br><span class='muted'>Accepted customers and onboarding state.</span></a>
          <a href='/agency/projects'><strong>Client projects</strong><br><span class='muted'>Audits, findings, reports, remediation and monitoring.</span></a>
          <a href='/agency/recurring-services'><strong>Presence Care</strong><br><span class='muted'>Recurring service lifecycle and delivery evidence.</span></a>
        </div></section>
        <p class='notice'><strong>Local product boundary:</strong> this runtime is private to Webify on this PC. Hosted SaaS signup, VERIDRA plans, billing and tenant-seat administration are intentionally not part of the workflow.</p>
        """
        return _page(body, title="Webify · VERIDRA local agency")

    if _operator_mode():
        body = f"""
        {agency_navigation(identity, current="home")}
        <div class='top'><div><p class='eyebrow'>VERIDRA operator</p><h1>Find opportunities, qualify them, audit evidence and turn the best ones into client work</h1>
        <p class='muted'>This is the operator workflow for Webify. Start with prospect discovery unless you already have a website you want to audit directly.</p></div>
        <div class='actions'><a class='button' href='/agency/prospects/discover'>Find prospects</a><a class='button secondary' href='/agency/prospects'>Review prospects</a></div></div>
        <div class='steps'>
          <div class='step'><strong>1. Discover</strong><span class='muted'>Find businesses worth reviewing.</span></div>
          <div class='step'><strong>2. Qualify</strong><span class='muted'>Prioritise commercial fit.</span></div>
          <div class='step'><strong>3. Audit</strong><span class='muted'>Collect bounded website evidence.</span></div>
          <div class='step'><strong>4. Win work</strong><span class='muted'>Use evidence in conversations and proposals.</span></div>
          <div class='step'><strong>5. Prove</strong><span class='muted'>Re-audit completed improvement work.</span></div>
        </div>
        <div class='grid'>
          <section><p class='eyebrow'>Primary workflow</p><h2>Prospect discovery</h2>
          <p>Search real businesses, review observed opportunities and add only worthwhile candidates to the prospect pipeline.</p>
          <div class='actions'><a class='button' href='/agency/prospects/discover'>Find prospects</a><a class='button secondary' href='/agency/prospects'>Open prospect pipeline</a></div></section>
          <section><p class='eyebrow'>Direct review</p><h2>Quick audit</h2>
          <p class='muted'>Use this only when you already know the website you want to inspect.</p>
          <form method='get' action='/agency/quick-audit'><label for='target'><strong>Public website</strong></label>
          <input id='target' name='target' maxlength='2048' placeholder='example.com' required>
          <button type='submit'>Start quick audit</button></form></section>
        </div>
        <section><h2>Ongoing work</h2><div class='links'>
          <a href='/agency/prospects'><strong>Prospects</strong><br><span class='muted'>Businesses being researched and qualified before outreach.</span></a>
          <a href='/agency/deals'><strong>Sales / proposals</strong><br><span class='muted'>Conversations, proposals and commercial progression.</span></a>
          <a href='/agency/customers'><strong>Customers</strong><br><span class='muted'>Accepted customers and onboarding state.</span></a>
          <a href='/agency/projects'><strong>Client projects</strong><br><span class='muted'>Assessments, reports, remediation, monitoring and proof.</span></a>
          <a href='/agency/recurring-services'><strong>Presence Care</strong><br><span class='muted'>Recurring services, billing state and lifecycle.</span></a>
        </div></section>
        <p class='notice'><strong>Operator rule:</strong> discovery creates prospect candidates; qualification decides whether deeper audit effort is justified. Real outreach remains a separate compliance-controlled action.</p>
        """
        return _page(body, title="VERIDRA operator")

    (
        white_label,
        embedded_forms,
        monitoring,
        audit_allowed,
        project_capacity,
    ) = _hosted_plan_state(request, identity)
    report_capability = (
        "Create branded white-label reports."
        if white_label
        else "Use standard Veridra reports. White-label branding unlocks on Professional."
    )
    monitoring_capability = (
        "Recurring monitoring is available on the active plan."
        if monitoring
        else "Recurring monitoring is locked on the active plan."
    )
    lead_forms_card = (
        "<a href='/agency/lead-forms'><strong>Lead forms</strong><br>"
        "<span class='muted'>Create embedded website-audit forms for your own agency site.</span></a>"
        if embedded_forms
        else "<a href='/billing'><strong>Lead forms · locked</strong><br>"
        "<span class='muted'>Embedded audit forms require the Agency plan. Review upgrade options.</span></a>"
    )
    audit_panel = (
        "<p class='muted'>Inspect a public website now. The result remains temporary until you explicitly create a client project.</p>"
        "<form method='get' action='/agency/quick-audit'><label for='target'><strong>Public website</strong></label>"
        "<input id='target' name='target' maxlength='2048' placeholder='example.com' required>"
        "<button type='submit'>Run audit</button></form>"
        if audit_allowed
        else "<p class='notice'><strong>Audit allowance unavailable.</strong> The workspace is suspended or the monthly audit allowance is exhausted. <a href='/workspace'>Review plan & usage</a>.</p>"
    )
    project_capacity_note = (
        "Project capacity is available."
        if project_capacity
        else "Project capacity is exhausted or the workspace is suspended. Existing projects remain available; review Plan & usage before converting another audit."
    )
    body = f"""
    {agency_navigation(identity, current="home")}
    <div class='top'><div><p class='eyebrow'>VERIDRA agency workspace</p><h1>Audit websites, deliver branded evidence and turn findings into client work</h1>
    <p class='muted'>Run evidence-backed audits, manage client projects and prove improvements over time. {report_capability} {monitoring_capability}</p></div>
    <div class='actions'><a class='button' href='/agency/projects'>Open projects</a><a class='button secondary' href='/agency/leads'>Review inbound leads</a></div></div>
    <div class='grid'>
      <section><p class='eyebrow'>Start here</p><h2>Run a website audit</h2>
      {audit_panel}</section>
      <section><p class='eyebrow'>Client delivery</p><h2>Projects and reports</h2>
      <p>Open persistent client projects to review assessments and manage remediation. {project_capacity_note} {report_capability} {monitoring_capability}</p>
      <div class='actions'><a class='button' href='/agency/projects'>Client projects</a></div></section>
    </div>
    <section><h2>Agency tools</h2><div class='links'>
      <a href='/agency/leads'><strong>Inbound leads</strong><br><span class='muted'>Qualify audit leads, record follow-up and convert won opportunities into projects.</span></a>
      {lead_forms_card}
      <a href='/agency/projects'><strong>Reports & monitoring</strong><br><span class='muted'>Open a project to prepare report output and compare assessments. {report_capability} {monitoring_capability}</span></a>
      <a href='/workspace'><strong>Plan & usage</strong><br><span class='muted'>Review project capacity, audit usage, PDF allowance and other workspace entitlements.</span></a>
      <a href='/billing'><strong>Billing</strong><br><span class='muted'>Manage a paid subscription through the configured billing provider.</span></a>
      <a href='/workspace/members'><strong>Team</strong><br><span class='muted'>Manage workspace members within the plan seat allowance.</span></a>
    </div></section>
    <p class='notice'><strong>Evidence boundary:</strong> VERIDRA uses bounded public observations. Reports do not claim penetration testing, universal AI visibility, backlink intelligence or traffic/rank data that VERIDRA does not collect.</p>
    """
    return _page(body, title="VERIDRA agency workspace")


@router.get("/agency/quick-audit")
def quick_audit_handoff(
    target: str = Query(min_length=1, max_length=2048),
) -> RedirectResponse:
    cleaned = target.strip()
    if not cleaned:
        return RedirectResponse("/agency", status_code=303)
    return RedirectResponse(f"/agency/audit?{urlencode({'url': cleaned})}", status_code=303)
