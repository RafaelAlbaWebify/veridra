from __future__ import annotations

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .workspace_policy import PLAN_CATALOGUE, PlanEntitlements, PlanName

router = APIRouter(tags=["plans"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f6f7f9;color:#17202a;font:15px Arial,sans-serif}a{color:inherit}header{background:#fff;border-bottom:1px solid #e1e5ea}.nav{max-width:1180px;margin:auto;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;gap:18px}.brand{font-size:23px;font-weight:800;text-decoration:none}.nav-actions{display:flex;align-items:center;gap:14px}.nav-actions a{text-decoration:none;font-weight:700}.button{display:inline-block;border-radius:8px;background:#1f2933;color:#fff;padding:12px 17px;text-decoration:none;font-weight:700}main{max-width:1180px;margin:auto;padding:56px 24px 72px}.hero{text-align:center;max-width:780px;margin:0 auto 36px}.hero h1{font-size:42px;margin:0 0 16px}.hero p{font-size:18px;line-height:1.55;color:#5f6975}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.card{background:#fff;border:1px solid #dfe4ea;border-radius:12px;padding:24px;display:flex;flex-direction:column}.card h2{margin:4px 0 8px}.eyebrow{text-transform:uppercase;letter-spacing:.08em;font-size:11px;color:#66717d;font-weight:700}.price-note{min-height:48px;color:#59636f;line-height:1.45}.limits{list-style:none;padding:0;margin:18px 0 22px}.limits li{padding:8px 0;border-bottom:1px solid #edf0f3;line-height:1.35}.limits strong{display:block}.card .button{margin-top:auto;text-align:center}.foot{margin-top:28px;background:#eef2f6;border-radius:10px;padding:20px;color:#4d5965;line-height:1.55}@media(max-width:1000px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){main{padding:36px 16px 56px}.hero h1{font-size:34px}.grid{grid-template-columns:1fr}.nav{align-items:flex-start}.nav-actions{flex-direction:column;align-items:flex-end;gap:8px}}
"""


def _number(value: int) -> str:
    return f"{value:,}"


def _yes_no(value: bool) -> str:
    return "Included" if value else "Not included"


def _card(plan: PlanName, entitlements: PlanEntitlements) -> str:
    label = plan.value.title()
    price_note = (
        "Free workspace · no payment required."
        if plan is PlanName.free
        else "Paid plan · the configured Stripe price is shown in secure checkout after signup."
    )
    features = (
        ("Client projects", _number(entitlements.max_projects)),
        ("Monthly audits", _number(entitlements.monthly_audits)),
        ("Monthly crawled pages", _number(entitlements.monthly_crawled_pages)),
        ("Monthly PDFs", _number(entitlements.monthly_pdfs)),
        ("Monthly exports", _number(entitlements.monthly_exports)),
        ("Monthly monitoring runs", _number(entitlements.monthly_monitoring_runs)),
        ("Monthly lead submissions", _number(entitlements.monthly_lead_submissions)),
        ("White-label reports", _yes_no(entitlements.white_label)),
        ("Embedded lead forms", _yes_no(entitlements.embedded_lead_forms)),
        ("Users", _number(entitlements.max_users)),
    )
    rows = "".join(
        f"<li><strong>{html.escape(name)}</strong>{html.escape(value)}</li>"
        for name, value in features
    )
    return (
        f"<article class='card' data-plan='{html.escape(plan.value)}'>"
        f"<span class='eyebrow'>Veridra plan</span><h2>{html.escape(label)}</h2>"
        f"<p class='price-note'>{html.escape(price_note)}</p>"
        f"<ul class='limits'>{rows}</ul>"
        "<a class='button' href='/signup'>Create free workspace</a></article>"
    )


@router.get("/plans", response_class=HTMLResponse)
def plans() -> str:
    cards = "".join(_card(plan, PLAN_CATALOGUE[plan]) for plan in PlanName)
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Veridra plans</title><style>{_STYLE}</style></head><body><header><div class='nav'><a class='brand' href='/free'>Veridra</a><div class='nav-actions'><a href='/free'>Free tools</a><a href='/login'>Sign in</a><a class='button' href='/signup'>Create workspace</a></div></div></header><main><section class='hero'><span class='eyebrow'>Plans</span><h1>Choose the workspace capacity you need</h1><p>Every plan uses the same evidence-first audit model. Higher plans add client capacity, reporting, monitoring, team seats and agency lead-generation features.</p></section><section class='grid'>{cards}</section><div class='foot'><strong>Billing transparency:</strong> Veridra does not hard-code a second copy of paid prices in this page. Paid amounts and billing intervals come from the Stripe Prices configured for the deployment and are shown in Stripe Checkout. Start on Free, then upgrade from the authenticated billing page when you are ready.</div></main></body></html>"""
