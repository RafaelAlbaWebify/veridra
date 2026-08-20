# ruff: noqa: E501
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse

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
def agency_workflow_home() -> str:
    body = """
    <div class='top'><div><p class='eyebrow'>Agency workspace</p><h1>Turn website evidence into client work</h1>
    <p class='muted'>Run an audit, produce a branded report, organise remediation and prove improvement through monitoring.</p></div>
    <div class='actions'><a class='button secondary' href='/workspace'>Plan and usage</a><a class='button secondary' href='/workspace/members'>Team</a></div></div>
    <div class='steps'>
      <div class='step'><strong>1. Audit</strong><span class='muted'>Collect bounded public evidence.</span></div>
      <div class='step'><strong>2. Explain</strong><span class='muted'>Review findings and priorities.</span></div>
      <div class='step'><strong>3. Report</strong><span class='muted'>Create branded client output.</span></div>
      <div class='step'><strong>4. Remediate</strong><span class='muted'>Convert findings into tasks.</span></div>
      <div class='step'><strong>5. Prove</strong><span class='muted'>Rescan and compare changes.</span></div>
    </div>
    <div class='grid'>
      <section><p class='eyebrow'>One-off opportunity</p><h2>Quick audit</h2>
      <p>Use this for a prospect or an initial review. The handoff starts the existing bounded assessment and does not create a project or save data automatically.</p>
      <form method='get' action='/agency/quick-audit'><label for='target'><strong>Public website</strong></label>
      <input id='target' name='target' maxlength='2048' placeholder='example.com' required>
      <button type='submit'>Start quick audit</button></form></section>
      <section><p class='eyebrow'>Ongoing client work</p><h2>Client projects</h2>
      <p>Open persistent tenant projects for saved evidence, branded reports, remediation, monitoring and comparison.</p>
      <div class='actions'><a class='button' href='/agency/projects'>Open client projects</a></div></section>
    </div>
    <section><h2>Agency operations</h2><p class='muted'>Normal agency work stays inside tenant-qualified project, lead and workspace routes.</p>
    <div class='links'>
      <a href='/agency/projects'><strong>Client projects</strong><br><span class='muted'>Open saved assessments, branded report profiles and outputs, remediation and monitoring.</span></a>
      <a href='/agency/leads'><strong>Leads</strong><br><span class='muted'>Review captured prospects, qualify follow-up and convert accepted work into client projects.</span></a>
      <a href='/agency/lead-forms'><strong>Lead forms</strong><br><span class='muted'>Configure tenant-owned embedded capture.</span></a>
      <a href='/workspace'><strong>Workspace controls</strong><br><span class='muted'>Review plan, usage, permissions and plan-change history.</span></a>
      <a href='/workspace/members'><strong>Team</strong><br><span class='muted'>Manage tenant members and roles.</span></a>
    </div></section>
    <p class='notice'><strong>Boundary:</strong> A quick audit is temporary until an operator explicitly creates a client project. Veridra does not infer a tenant, client or project from a submitted URL. Persistent work should continue from the tenant-qualified client-project index.</p>
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
