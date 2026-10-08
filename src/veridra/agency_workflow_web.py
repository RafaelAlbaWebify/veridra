# ruff: noqa: E501
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .agency_navigation import agency_navigation
from .agency_ui import help_tip
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
.local-home main{padding-top:22px;padding-bottom:20px}
.local-home .top{align-items:center;margin-bottom:12px}
.local-home .top h1{font-size:26px;line-height:1.15;margin:3px 0 5px}
.local-home .top p{margin:0}
.local-home .flow-strip{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px;margin:10px 0 12px}
.local-home .flow-step{display:flex;align-items:center;gap:8px;background:#fff;border:1px solid #dfe3e8;border-radius:8px;padding:9px 10px;min-width:0}
.local-home .flow-number{display:grid;place-items:center;flex:0 0 24px;height:24px;border-radius:999px;background:#eef1f4;font-size:11px;font-weight:700;color:#4c5661}
.local-home .flow-step strong{font-size:13px;white-space:nowrap}
.local-home .local-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.local-home .local-grid section{padding:16px;min-height:235px;display:flex;flex-direction:column}
.local-home .local-grid h2{font-size:18px;margin:5px 0 8px}
.local-home .local-grid p{line-height:1.4;margin:0 0 12px}
.local-home .local-grid .actions{margin-top:auto}
.local-home .local-grid form{margin-top:auto}
.local-home .local-grid input{margin:5px 0 8px;padding:9px}
.local-home .local-grid .button,.local-home .local-grid button{padding:9px 11px}
.local-home .boundary-line{margin:10px 0 0;padding:8px 10px;border-top:1px solid #dfe3e8;color:#68707a;font-size:12px}
.local-home .boundary-line strong{color:#404850}
@media(max-width:1320px){.local-home .local-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){.steps{grid-template-columns:1fr 1fr}.links{grid-template-columns:1fr 1fr}.local-home .flow-strip{grid-template-columns:1fr 1fr 1fr}}
@media(max-width:680px){.top,.grid{display:block}.card,section{margin-bottom:14px}.steps,.links,.local-home .flow-strip,.local-home .local-grid{grid-template-columns:1fr}}
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
        <div class='agency-workbench'><div class='workbench-scroll local-home'>
        <div class='top'><div><p class='eyebrow'>WEBIFY · VERIDRA LOCAL</p><h1>Sales, website audits and client delivery in one workspace</h1>
        <p class='muted'>Private Webify workspace · local only · no VERIDRA subscription or SaaS plan.</p></div>
        <div class='actions'><a class='button' href='/agency/prospects/discover'>Find prospects</a><a class='button secondary' href='/agency/projects'>Client projects</a></div></div>

        <div class='flow-strip' aria-label='Webify workflow'>
          <div class='flow-step'><span class='flow-number'>1</span><strong>Find</strong></div>
          <div class='flow-step'><span class='flow-number'>2</span><strong>Qualify</strong></div>
          <div class='flow-step'><span class='flow-number'>3</span><strong>Audit</strong></div>
          <div class='flow-step'><span class='flow-number'>4</span><strong>Deliver</strong></div>
          <div class='flow-step'><span class='flow-number'>5</span><strong>Prove</strong></div>
        </div>

        <div class='local-grid'>
          <section><p class='eyebrow'>Outbound / research</p><h2>Prospects</h2>
          <p>Discover businesses, qualify opportunities and move worthwhile candidates into Webify's sales pipeline.</p>
          <div class='actions'><a class='button' href='/agency/prospects/discover'>Find prospects</a><a class='button secondary' href='/agency/prospects'>Pipeline</a></div></section>

          <section><p class='eyebrow'>Direct website review</p><h2>Audit</h2>
          <p class='muted'>Inspect a known public website and turn useful evidence into client work.</p>
          <form method='get' action='/agency/quick-audit'><label for='target'><strong>Public website</strong></label>
          <input id='target' name='target' maxlength='2048' placeholder='example.com' required>
          <button type='submit'>Run audit</button></form></section>

          <section><p class='eyebrow'>Inbound</p><h2>Leads</h2>
          <p>Review inbound audit leads and manage Webify-branded website-audit forms.</p>
          <div class='actions'><a class='button' href='/agency/leads'>Inbound leads</a><a class='button secondary' href='/agency/lead-forms'>Lead forms</a></div></section>

          <section><p class='eyebrow'>Delivery</p><h2>Client work</h2>
          <p>Manage customers, projects, reports, remediation, monitoring and recurring Presence Care.</p>
          <div class='actions'><a class='button' href='/agency/customers'>Customers</a><a class='button secondary' href='/agency/projects'>Projects</a></div></section>
        </div>

        <p class='boundary-line'><strong>Private local runtime.</strong> Hosted SaaS signup, VERIDRA plans, billing and tenant-seat administration are not part of this workflow.</p>
        </div></div>
        """
        return _page(body, title="Webify · VERIDRA local agency")

    if _operator_mode():
        qualification_help = help_tip(
            "Qualification means deciding whether a prospect is worth deeper audit and sales effort.",
            label="Qualification",
        )
        evidence_help = help_tip(
            "Evidence is a saved, observable fact from the website or supported provider. It is not a guess.",
            label="Evidence",
        )
        presence_help = help_tip(
            "Presence Care is Webify's recurring post-delivery monitoring and minor-fix service.",
            label="Presence Care",
        )
        body = f"""
        {agency_navigation(identity, current="home")}
        <div class='agency-workbench'><div class='operator-command'>
          <div class='operator-hero'>
            <section class='operator-primary'>
              <p class='eyebrow'>Operator command center</p>
              <h1>Start with the next useful action, not the system internals.</h1>
              <p>VERIDRA guides Webify from finding an opportunity to proving completed work. If you are starting a new sales cycle, begin with prospect discovery. If you already know the website, use a quick audit.</p>
              <div class='actions'>
                <a class='button' href='/agency/prospects/discover'
                   title='Find businesses and review them before adding worthwhile candidates to the pipeline'
                   data-help='Find businesses and review them before adding worthwhile candidates to the pipeline'>Find prospects</a>
                <a class='button secondary' href='/agency/prospects'
                   title='Open prospects already saved for qualification or follow-up'
                   data-help='Open prospects already saved for qualification or follow-up'>Open prospect pipeline</a>
              </div>
            </section>
            <aside class='operator-guide'>
              <p class='eyebrow'>What should I do?</p>
              <h2>Follow the workflow from left to right</h2>
              <p>Each stage has one job. VERIDRA keeps missing or incomplete information visible instead of pretending it is complete.</p>
              <p class='guardrail'><strong>Important:</strong> finding or qualifying a prospect does not authorise outreach. Real outreach remains compliance-controlled.</p>
            </aside>
          </div>

          <div class='operator-flow' aria-label='Webify operator workflow'>
            <div class='step'><strong>1. Discover</strong><span class='muted'>Find businesses worth reviewing.</span></div>
            <div class='step'><strong>2. Qualify {qualification_help}</strong><span class='muted'>Decide whether deeper work is justified.</span></div>
            <div class='step'><strong>3. Audit {evidence_help}</strong><span class='muted'>Collect bounded, reviewable evidence.</span></div>
            <div class='step'><strong>4. Win work</strong><span class='muted'>Progress conversations and proposals.</span></div>
            <div class='step'><strong>5. Prove</strong><span class='muted'>Re-check completed work and preserve proof.</span></div>
          </div>

          <div class='operator-modules'>
            <section class='operator-module'>
              <p class='eyebrow'>Primary workflow</p>
              <h2>Prospects</h2>
              <p>Discover, review and qualify businesses before sales effort is spent.</p>
              <div class='actions'>
                <a class='button' href='/agency/prospects/discover' title='Start a new prospect discovery'>Find prospects</a>
                <a class='button secondary' href='/agency/prospects' title='Review saved prospects'>Pipeline</a>
              </div>
            </section>

            <section class='operator-module'>
              <p class='eyebrow'>Known website</p>
              <h2>Quick audit</h2>
              <p>Use this when you already know which public website you want VERIDRA to inspect.</p>
              <form method='get' action='/agency/quick-audit'>
                <label for='target'><strong>Public website</strong></label>
                <input id='target' name='target' maxlength='2048' placeholder='example.com' required
                       title='Enter the public website you want to inspect'>
                <button type='submit' title='Run a temporary audit of this public website'>Start quick audit</button>
              </form>
            </section>

            <section class='operator-module'>
              <p class='eyebrow'>Commercial</p>
              <h2>Sales & customers</h2>
              <p>Move qualified opportunities through conversations, proposals, acceptance and onboarding.</p>
              <div class='actions'>
                <a class='button' href='/agency/deals' title='Open sales conversations and proposals'>Sales / proposals</a>
                <a class='button secondary' href='/agency/customers' title='Open accepted customers and onboarding state'>Customers</a>
              </div>
            </section>

            <section class='operator-module'>
              <p class='eyebrow'>Delivery & recurring</p>
              <h2>Client work {presence_help}</h2>
              <p>Run assessments, remediation, reporting, proof and recurring Presence Care after work is accepted.</p>
              <div class='actions'>
                <a class='button' href='/agency/projects' title='Open client delivery projects'>Client projects</a>
                <a class='button secondary' href='/agency/recurring-services' title='Open recurring Presence Care services'>Presence Care</a>
              </div>
            </section>
          </div>
        </div></div>
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
    <div class='agency-workbench'><div class='workbench-scroll'>
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
    </div></div>
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
