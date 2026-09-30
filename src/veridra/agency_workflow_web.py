# ruff: noqa: E501
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .agency_navigation import agency_navigation
from .request_security import require_request_identity

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


def _page(body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Agency workflow · Veridra</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


@router.get("/agency", response_class=HTMLResponse)
def agency_workflow_home(request: Request) -> str:
    identity = require_request_identity(request)
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
    return _page(body)


@router.get("/agency/quick-audit")
def quick_audit_handoff(
    target: str = Query(min_length=1, max_length=2048),
) -> RedirectResponse:
    cleaned = target.strip()
    if not cleaned:
        return RedirectResponse("/agency", status_code=303)
    return RedirectResponse(f"/agency/audit?{urlencode({'url': cleaned})}", status_code=303)
