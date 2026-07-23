# ruff: noqa: E501
from __future__ import annotations

import csv
import html
import io
from datetime import UTC, datetime
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .workspace_policy import (
    PLAN_CATALOGUE,
    PlanName,
    UsageEvent,
    UsageKind,
    UsageLedger,
    WorkspaceConfig,
    WorkspacePolicyError,
    WorkspaceStatus,
    WorkspaceStore,
    quota_decision,
    usage_period,
)

router = APIRouter(prefix="/workspace", tags=["workspace policy"])

_STYLE = """
body{font:14px Arial;margin:0;background:#f7f8fa;color:#17191c}main{max-width:1180px;margin:36px auto;padding:0 20px}
section{background:#fff;border:1px solid #dfe3e8;border-radius:8px;padding:22px;margin-bottom:18px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.metric{border:1px solid #dfe3e8;padding:15px}.metric strong{display:block;font-size:24px;margin-top:6px}table{width:100%;border-collapse:collapse}th,td{padding:10px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}
label{display:block;font-weight:700;margin:10px 0 4px}input,select{width:100%;padding:9px;border:1px solid #cfd4da}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.button,button{display:inline-block;background:#22272d;color:#fff;border:0;padding:9px 12px;text-decoration:none;cursor:pointer}.muted{color:#68707a}.warn{color:#9a6700}@media(max-width:760px){.grid,.row{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main><p><a href='/workspace'>Workspace</a> · <a href='/commercial'>Commercial operations</a> · <a href='/projects'>Projects</a> · <a href='/'>Assessment console</a></p>{body}</main></body></html>"


def _single(body: bytes, name: str) -> str:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True).get(name, [""])[0].strip()


def _store() -> WorkspaceStore:
    return WorkspaceStore()


def _ledger() -> UsageLedger:
    return UsageLedger()


def _summary_rows(workspace: WorkspaceConfig, now: datetime) -> str:
    ledger = _ledger()
    rows: list[str] = []
    for kind in UsageKind:
        decision = quota_decision(workspace, ledger, kind, requested=1, now=now)
        limit = "Metered only" if decision.limit is None else str(decision.limit)
        remaining = "—" if decision.remaining is None else str(decision.remaining)
        rows.append(
            f"<tr><td>{html.escape(kind.value.replace('_', ' ').title())}</td><td>{decision.used}</td><td>{limit}</td><td>{remaining}</td><td>{html.escape(decision.reason)}</td></tr>"
        )
    return "".join(rows)


@router.get("", response_class=HTMLResponse)
def workspace_dashboard() -> str:
    workspace = _store().load()
    entitlement = PLAN_CATALOGUE[workspace.plan]
    now = datetime.now(UTC)
    period = usage_period(workspace, now=now)
    body = f"""<section><h1>{html.escape(workspace.display_name)}</h1><p><strong>Plan:</strong> {workspace.plan.value.title()} · <strong>Status:</strong> {workspace.status.value.title()}<br><strong>Current cycle:</strong> {period.starts_at.isoformat()} to {period.ends_at.isoformat()}</p><p class='muted'>This is a local policy and metering layer. It is not authentication, tenant isolation, payment collection or production subscription enforcement.</p><p><a class='button' href='/workspace/usage.csv'>Export usage CSV</a></p></section><section><h2>Current entitlements</h2><div class='grid'><article class='metric'>Projects<strong>{entitlement.max_projects}</strong></article><article class='metric'>Users<strong>{entitlement.max_users}</strong></article><article class='metric'>White label<strong>{'Yes' if entitlement.white_label else 'No'}</strong></article><article class='metric'>Embedded forms<strong>{'Yes' if entitlement.embedded_lead_forms else 'No'}</strong></article></div></section><section><h2>Usage and allowance</h2><table><thead><tr><th>Resource</th><th>Used</th><th>Limit</th><th>Remaining</th><th>Decision</th></tr></thead><tbody>{_summary_rows(workspace, now)}</tbody></table></section><section><h2>Preview or apply plan</h2><form method='get' action='/workspace/plan-preview'><div class='row'><div><label>Plan</label><select name='plan'>{''.join(f"<option value='{plan.value}'{' selected' if plan == workspace.plan else ''}>{plan.value.title()}</option>" for plan in PlanName)}</select></div><div><label>Cycle anchor day</label><input type='number' min='1' max='28' name='cycle_anchor_day' value='{workspace.cycle_anchor_day}'></div></div><p><button>Preview plan</button></p></form></section>"""
    return _page("Workspace usage", body)


@router.get("/plan-preview", response_class=HTMLResponse)
def plan_preview(plan: PlanName, cycle_anchor_day: int = 1) -> str:
    current = _store().load()
    try:
        proposed = WorkspaceConfig(
            display_name=current.display_name,
            plan=plan,
            status=current.status,
            cycle_anchor_day=cycle_anchor_day,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace plan configuration.") from exc
    entitlement = PLAN_CATALOGUE[proposed.plan]
    rows = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td></tr>"
        for label, value in (
            ("Projects", str(entitlement.max_projects)),
            ("Monthly audits", str(entitlement.monthly_audits)),
            ("Monthly crawled-page reservation", str(entitlement.monthly_crawled_pages)),
            ("Monthly PDFs", str(entitlement.monthly_pdfs)),
            ("Monthly exports", str(entitlement.monthly_exports)),
            ("Monthly lead submissions", str(entitlement.monthly_lead_submissions)),
            ("Monthly monitoring runs", str(entitlement.monthly_monitoring_runs)),
            ("White label", "Yes" if entitlement.white_label else "No"),
            ("Embedded lead forms", "Yes" if entitlement.embedded_lead_forms else "No"),
            ("Users", str(entitlement.max_users)),
        )
    )
    body = f"<section><h1>Plan preview: {proposed.plan.value.title()}</h1><p class='muted'>Changing the local plan does not charge a payment method or create a subscription.</p><table><tbody>{rows}</tbody></table><form method='post' action='/workspace/plan'><input type='hidden' name='plan' value='{proposed.plan.value}'><input type='hidden' name='cycle_anchor_day' value='{proposed.cycle_anchor_day}'><p><button>Apply local plan</button></p></form></section>"
    return _page("Plan preview", body)


@router.post("/plan")
async def apply_plan(request: Request) -> RedirectResponse:
    body = await request.body()
    current = _store().load()
    try:
        updated = WorkspaceConfig(
            display_name=current.display_name,
            plan=PlanName(_single(body, "plan")),
            status=WorkspaceStatus.active,
            cycle_anchor_day=int(_single(body, "cycle_anchor_day")),
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace plan configuration.") from exc
    _store().save(updated)
    return RedirectResponse("/workspace", status_code=303)


@router.get("/usage.csv")
def usage_csv() -> Response:
    workspace = _store().load()
    period = usage_period(workspace)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["event_id", "kind", "quantity", "occurred_at", "related_id", "note"])
    for identifier, event in _ledger().list(period=period):
        writer.writerow([identifier, event.kind.value, event.quantity, event.occurred_at.isoformat(), event.related_id, event.note])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=veridra-usage.csv"})


def reserve_usage(kind: UsageKind, *, quantity: int = 1) -> None:
    workspace = _store().load()
    decision = quota_decision(workspace, _ledger(), kind, requested=quantity)
    if not decision.allowed:
        raise HTTPException(status_code=429, detail=decision.reason)


def record_usage(kind: UsageKind, *, quantity: int = 1, related_id: str = "", note: str = "") -> str:
    try:
        return _ledger().record(
            UsageEvent(
                kind=kind,
                quantity=quantity,
                occurred_at=datetime.now(UTC),
                related_id=related_id,
                note=note,
            )
        )
    except WorkspacePolicyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
