# ruff: noqa: E501
from __future__ import annotations

import html
import os
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .agency_navigation import agency_navigation
from .customer_store import CustomerRecord, CustomerSourceType
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .recurring_service import (
    BillingCadence,
    RecurringServiceEvent,
    RecurringServiceRecord,
    RecurringServiceStatus,
    RecurringServiceVersion,
    RenewalBehavior,
)
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .tenant_customer_store import TenantCustomerStore
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .tenant_recurring_service_store import TenantRecurringServiceStore

router = APIRouter(prefix="/agency", tags=["agency-recurring-service"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1040px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:22px;margin-bottom:18px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}label{display:block;font-weight:700;margin:10px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:90px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.success{border-left-color:#16794a;background:#f0faf5}.warning{border-left-color:#946200;background:#fff9e8}.danger{border-left-color:#b42318;background:#fff1f0}.actions{display:flex;gap:8px;flex-wrap:wrap}.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}.checklist{list-style:none;padding:0}.checklist li{padding:7px 0;border-bottom:1px solid #e8eaed}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #e8eaed;vertical-align:top}th{font-size:12px;text-transform:uppercase;color:#68707a}@media(max-width:760px){.row,.three{grid-template-columns:1fr}}
"""


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _lines(values: dict[str, list[str]], name: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in _one(values, name).splitlines()
        if line.strip()
    )


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Recurring service workflow is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Recurring service request is not permitted.") from exc


def _identity(request: Request, capability: TenantCapability = TenantCapability.view_data) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, capability)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    return identity


def _project_exists(request: Request, identity: RequestIdentity, project_id: str) -> None:
    store = TenantProjectStore(_root(request))
    try:
        store.load(identity, store.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


def _linked_customer(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
) -> tuple[str, CustomerRecord]:
    linked = [
        item
        for item in TenantCustomerStore(_root(request)).list(identity)
        if project_id in item[1].project_ids
    ]
    if not linked:
        raise HTTPException(status_code=409, detail="Project must be linked to a customer first.")
    if len(linked) > 1:
        raise HTTPException(status_code=409, detail="Recurring service requires one unambiguous linked customer.")
    return linked[0]


def _change_request_link(customer: CustomerRecord) -> str:
    if customer.source_type is CustomerSourceType.prospect:
        return f"/agency/prospects/{html.escape(customer.source_id, quote=True)}/deal/change-requests"
    return "/agency/deals"


def _status_label(value: str) -> str:
    return value.replace("_", " ").title()


def _event(record: RecurringServiceRecord, action: str, reference: str = "") -> tuple[RecurringServiceEvent, ...]:
    return (*record.events, RecurringServiceEvent(action=action, reference=reference))


def _save(
    request: Request,
    identity: RequestIdentity,
    record: RecurringServiceRecord,
    updates: dict[str, object],
    *,
    action: str,
    reference: str = "",
) -> None:
    updates["events"] = _event(record, action, reference)
    try:
        updated = RecurringServiceRecord.model_validate(
            {**record.model_dump(mode="json"), **updates}
        )
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "Recurring service transition is invalid.")
        raise HTTPException(status_code=400, detail=str(message)) from exc
    TenantRecurringServiceStore(_root(request)).save(identity, updated)


def _parse_date(value: str, field: str, *, required: bool = False) -> date | None:
    if not value:
        if required:
            raise HTTPException(status_code=400, detail=f"{field} is required.")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be a valid date.") from exc


def _parse_money(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail="Recurring fee must be a valid amount.") from exc


def _version_summary(record: RecurringServiceRecord) -> str:
    version = record.active_version
    if version is None:
        return "<p class='muted'>No recurring plan version configured yet.</p>"
    scope = "".join(f"<li>{html.escape(item)}</li>" for item in version.scope) or "<li>None</li>"
    deliverables = "".join(f"<li>{html.escape(item)}</li>" for item in version.deliverables) or "<li>None</li>"
    exclusions = "".join(f"<li>{html.escape(item)}</li>" for item in version.exclusions) or "<li>None</li>"
    return f"""
<div class='three'><div><h3>Scope</h3><ul>{scope}</ul></div><div><h3>Deliverables</h3><ul>{deliverables}</ul></div><div><h3>Exclusions</h3><ul>{exclusions}</ul></div></div>
<p><strong>Version:</strong> {version.version} · <strong>Fee:</strong> {html.escape(str(version.fee))} {html.escape(version.currency)} / {html.escape(version.billing_cadence.value)} · <strong>Cadence:</strong> {html.escape(version.cadence_description or 'Not set')}</p>
<p><strong>Response:</strong> {html.escape(version.response_time or 'Not set')} · <strong>Escalation:</strong> {html.escape(version.escalation_expectations or 'Not set')}</p>"""


def _history(record: RecurringServiceRecord) -> str:
    if not record.events:
        return "<p class='muted'>No recurring lifecycle events yet.</p>"
    return "<ul class='checklist'>" + "".join(
        f"<li><strong>{html.escape(_status_label(item.action))}</strong> · {html.escape(item.at.isoformat())}"
        + (f"<br><span class='muted'>{html.escape(item.reference)}</span>" if item.reference else "")
        + "</li>"
        for item in reversed(record.events)
    ) + "</ul>"


def _configure_form(record: RecurringServiceRecord, *, renewal: bool = False) -> str:
    version = record.active_version
    scope = "\n".join(version.scope) if version else ""
    deliverables = "\n".join(version.deliverables) if version else ""
    exclusions = "\n".join(version.exclusions) if version else ""
    fee = str(version.fee) if version else "99.00"
    currency = version.currency if version else "EUR"
    cadence = version.billing_cadence.value if version else BillingCadence.monthly.value
    action = "renew" if renewal else "configure"
    heading = "Renew / change recurring plan" if renewal else "Configure recurring plan"
    submit = "Create new plan version" if renewal else "Save recurring plan"
    return f"""<section><h2>{heading}</h2><form method='post' action='recurring/{action}'>
<label>Service scope — one item per line</label><textarea name='scope' required>{html.escape(scope)}</textarea>
<div class='row'><div><label>Deliverables — one per line</label><textarea name='deliverables' required>{html.escape(deliverables)}</textarea></div><div><label>Exclusions — one per line</label><textarea name='exclusions'>{html.escape(exclusions)}</textarea></div></div>
<div class='three'><div><label>Recurring fee</label><input name='fee' value='{html.escape(fee, quote=True)}' required></div><div><label>Currency</label><input name='currency' maxlength='3' value='{html.escape(currency, quote=True)}' required></div><div><label>Billing cadence</label><select name='billing_cadence'><option value='monthly' {'selected' if cadence == 'monthly' else ''}>Monthly</option><option value='quarterly' {'selected' if cadence == 'quarterly' else ''}>Quarterly</option><option value='annually' {'selected' if cadence == 'annually' else ''}>Annually</option></select></div></div>
<label>Service / monitoring cadence</label><input name='cadence_description' value='{html.escape(version.cadence_description if version else '', quote=True)}' required>
<div class='row'><div><label>Response-time expectation</label><input name='response_time' value='{html.escape(version.response_time if version else '', quote=True)}'></div><div><label>Escalation expectation</label><input name='escalation_expectations' value='{html.escape(version.escalation_expectations if version else '', quote=True)}'></div></div>
<label>Effective from</label><input type='date' name='effective_from' value='{html.escape(str(version.effective_from) if version and version.effective_from else '', quote=True)}'>
{"<label>Renewal / scope-price change reference</label><textarea name='renewal_reference' required></textarea>" if renewal else ''}
<button type='submit'>{submit}</button></form></section>"""


def _actions(record: RecurringServiceRecord, customer: CustomerRecord) -> str:
    if record.status is RecurringServiceStatus.draft:
        return _configure_form(record) + ("<section><form method='post' action='recurring/offer'><button type='submit'>Mark plan offered</button></form></section>" if record.active_version else "")
    if record.status is RecurringServiceStatus.offered:
        return """<section><h2>Activate accepted recurring service</h2><form method='post' action='recurring/accept'><label>Acceptance evidence/reference</label><textarea name='acceptance_reference' required></textarea><div class='three'><div><label>Start date</label><input type='date' name='start_date' required></div><div><label>Next billing date</label><input type='date' name='next_billing_date' required></div><div><label>Renewal date</label><input type='date' name='renewal_date'></div></div><div class='three'><div><label>Minimum term (months)</label><input type='number' min='0' max='120' name='minimum_term_months' value='0'></div><div><label>Renewal behavior</label><select name='renewal_behavior'><option value='manual'>Manual decision</option><option value='auto_renew'>Auto renew</option><option value='fixed_term'>Fixed term</option></select></div><div><label>Monitoring cadence</label><input name='monitoring_cadence' value='Monthly'></div></div><label>Report cadence</label><input name='report_cadence' value='Monthly'><button type='submit'>Record acceptance & activate</button></form></section>"""
    if record.status is RecurringServiceStatus.cancelled:
        return "<section><p class='notice'>Recurring service is cancelled. Historical versions and evidence remain read-only.</p></section>"
    if record.status is RecurringServiceStatus.expired:
        return "<section><p class='notice'>Recurring service has expired. Create a new recurring agreement rather than silently reactivating this record.</p></section>"
    change_link = html.escape(_change_request_link(customer), quote=True)
    common = f"""<section><h2>Recurring operations</h2><div class='row'><form method='post' action='recurring/deliverable'><label>Completed recurring deliverable</label><input name='deliverable' required><label>Evidence/reference</label><input name='reference' required><button type='submit'>Record deliverable</button></form><form method='post' action='recurring/payment'><label>Invoice reference</label><input name='invoice_reference' required><label>Payment state</label><select name='payment_state'><option value='paid'>Paid</option><option value='failed'>Failed / overdue</option></select><label>Payment/provider reference</label><input name='payment_reference' required><label>Next billing date</label><input type='date' name='next_billing_date'><button type='submit'>Record billing state</button></form></div><p><a class='button secondary' href='{change_link}'>Out-of-scope / overage Change Request</a></p></section>"""
    if record.status is RecurringServiceStatus.active:
        return common + f"""<section><div class='row'><form method='post' action='recurring/pause'><h2>Pause service</h2><label>Pause reason/reference</label><textarea name='reference' required></textarea><button class='secondary' type='submit'>Pause</button></form><form method='post' action='recurring/cancel-notice'><h2>Cancellation notice</h2><label>Notice date</label><input type='date' name='notice_date' required><label>Requested effective date</label><input type='date' name='effective_date'><label>Notice/reference</label><textarea name='reference' required></textarea><button class='secondary' type='submit'>Record cancellation notice</button></form></div></section>{_configure_form(record, renewal=True)}"""
    if record.status is RecurringServiceStatus.paused:
        return common + "<section><p class='notice warning'>Service is paused; recurring work should not be treated as active.</p><form method='post' action='recurring/resume'><label>Resume evidence/reference</label><textarea name='reference' required></textarea><button type='submit'>Resume service</button></form></section>"
    if record.status is RecurringServiceStatus.payment_blocked:
        return common + "<section><p class='notice danger'>Service is payment-blocked. Record a paid billing state before normal delivery resumes.</p></section>"
    if record.status is RecurringServiceStatus.cancellation_pending:
        return """<section><p class='notice warning'>Cancellation is pending. Complete the exit/handoff boundary before final cancellation.</p><form method='post' action='recurring/cancel-complete'><label>Effective cancellation date</label><input type='date' name='effective_date' required><label>Exit / ownership-access handoff evidence</label><textarea name='exit_handoff_reference' required></textarea><button type='submit'>Complete cancellation</button></form></section>"""
    return common


@router.get("/projects/{project_id}/recurring", response_class=HTMLResponse)
def recurring_service_page(project_id: str, request: Request) -> str:
    identity = _identity(request)
    _project_exists(request, identity, project_id)
    customer_id, customer = _linked_customer(request, identity, project_id)
    record = TenantRecurringServiceStore(_root(request)).load_or_empty(identity, project_id, customer_id)
    next_billing = str(record.next_billing_date) if record.next_billing_date else "Not scheduled"
    renewal = str(record.renewal_date) if record.renewal_date else "Not scheduled"
    body = f"""{agency_navigation(identity, current='projects')}<section><p><a href='/agency/projects/{html.escape(project_id, quote=True)}'>← Project overview</a></p><h1>Recurring service</h1><p><strong>Customer:</strong> {html.escape(customer.business_name)} · <span class='badge'>{html.escape(_status_label(record.status.value))}</span></p><p><strong>Next billing:</strong> {html.escape(next_billing)} · <strong>Renewal:</strong> {html.escape(renewal)} · <strong>Next action:</strong> {html.escape(record.next_action or 'Not set')}</p></section><section><h2>Current plan</h2>{_version_summary(record)}</section>{_actions(record, customer)}<section><details><summary><strong>Recurring lifecycle history</strong></summary>{_history(record)}</details></section>"""
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Recurring service</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


@router.get("/recurring-services", response_class=HTMLResponse)
def recurring_service_index(request: Request) -> str:
    identity = _identity(request)
    store = TenantRecurringServiceStore(_root(request))
    records = store.list(identity)
    customer_names = {customer_id: customer.business_name for customer_id, customer in TenantCustomerStore(_root(request)).list(identity)}
    if records:
        rows = "".join(
            f"<tr><td><a href='/agency/projects/{html.escape(item.project_id, quote=True)}/recurring'>{html.escape(customer_names.get(item.customer_id, item.customer_id))}</a></td><td>{html.escape(_status_label(item.status.value))}</td><td>{html.escape(str(item.active_version.fee) + ' ' + item.active_version.currency if item.active_version else 'Not configured')}</td><td>{html.escape(str(item.next_billing_date) if item.next_billing_date else '—')}</td><td>{html.escape(item.next_action or '—')}</td></tr>"
            for item in records
        )
    else:
        rows = "<tr><td colspan='5' class='muted'>No recurring services configured yet.</td></tr>"
    body = f"""{agency_navigation(identity, current='customers')}<section><h1>Recurring revenue</h1><p class='muted'>Operational view of recurring service state, billing and next action.</p><table><thead><tr><th>Customer</th><th>Status</th><th>Fee</th><th>Next billing</th><th>Next action</th></tr></thead><tbody>{rows}</tbody></table></section>"""
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Recurring revenue</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _record_for_write(request: Request, project_id: str) -> tuple[RequestIdentity, str, CustomerRecord, RecurringServiceRecord]:
    identity = _identity(request, TenantCapability.manage_projects)
    _trusted_origin(request)
    _project_exists(request, identity, project_id)
    customer_id, customer = _linked_customer(request, identity, project_id)
    record = TenantRecurringServiceStore(_root(request)).load_or_empty(identity, project_id, customer_id)
    return identity, customer_id, customer, record


def _redirect(project_id: str) -> RedirectResponse:
    return RedirectResponse(f"/agency/projects/{project_id}/recurring", status_code=303)


@router.post("/projects/{project_id}/recurring/configure")
async def configure_recurring(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status is not RecurringServiceStatus.draft:
        raise HTTPException(status_code=409, detail="Only a draft recurring service can be configured directly.")
    values = _values(await request.body())
    try:
        cadence = BillingCadence(_one(values, "billing_cadence"))
        version = RecurringServiceVersion(
            version=max((item.version for item in record.versions), default=0) + 1,
            scope=_lines(values, "scope"),
            deliverables=_lines(values, "deliverables"),
            exclusions=_lines(values, "exclusions"),
            cadence_description=_one(values, "cadence_description"),
            response_time=_one(values, "response_time"),
            escalation_expectations=_one(values, "escalation_expectations"),
            fee=_parse_money(_one(values, "fee")),
            currency=_one(values, "currency").upper(),
            billing_cadence=cadence,
            effective_from=_parse_date(_one(values, "effective_from"), "Effective-from date"),
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Recurring plan configuration is invalid.") from exc
    _save(request, identity, record, {"versions": (*record.versions, version), "current_version": version.version}, action="plan_configured", reference=f"Version {version.version}")
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/offer")
async def offer_recurring(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status is not RecurringServiceStatus.draft or record.active_version is None:
        raise HTTPException(status_code=409, detail="A configured draft plan is required before offering recurring service.")
    _save(request, identity, record, {"status": RecurringServiceStatus.offered, "offered_at": datetime.now(UTC), "next_action": "Await customer recurring-service decision."}, action="plan_offered")
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/accept")
async def accept_recurring(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status is not RecurringServiceStatus.offered:
        raise HTTPException(status_code=409, detail="Only an offered recurring plan can be accepted.")
    values = _values(await request.body())
    reference = _one(values, "acceptance_reference")
    try:
        minimum = int(_one(values, "minimum_term_months") or "0")
        renewal_behavior = RenewalBehavior(_one(values, "renewal_behavior"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Recurring acceptance terms are invalid.") from exc
    _save(
        request,
        identity,
        record,
        {
            "status": RecurringServiceStatus.active,
            "accepted_at": datetime.now(UTC),
            "acceptance_reference": reference,
            "start_date": _parse_date(_one(values, "start_date"), "Start date", required=True),
            "minimum_term_months": minimum,
            "renewal_behavior": renewal_behavior,
            "renewal_date": _parse_date(_one(values, "renewal_date"), "Renewal date"),
            "next_billing_date": _parse_date(_one(values, "next_billing_date"), "Next billing date", required=True),
            "monitoring_cadence": _one(values, "monitoring_cadence"),
            "report_cadence": _one(values, "report_cadence"),
            "next_action": "Run the next recurring deliverable and maintain billing evidence.",
        },
        action="service_activated",
        reference=reference,
    )
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/deliverable")
async def recurring_deliverable(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status is not RecurringServiceStatus.active:
        raise HTTPException(status_code=409, detail="Recurring deliverables can only be recorded while service is active.")
    values = _values(await request.body())
    deliverable = _one(values, "deliverable")
    reference = _one(values, "reference")
    if not deliverable or not reference:
        raise HTTPException(status_code=400, detail="Deliverable and evidence/reference are required.")
    _save(request, identity, record, {"completed_deliverables": (*record.completed_deliverables, deliverable), "next_action": "Review next billing date and scheduled recurring deliverable."}, action="deliverable_completed", reference=f"{deliverable}: {reference}")
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/payment")
async def recurring_payment(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status not in {RecurringServiceStatus.active, RecurringServiceStatus.payment_blocked}:
        raise HTTPException(status_code=409, detail="Billing state can only be updated for active or payment-blocked service.")
    values = _values(await request.body())
    state = _one(values, "payment_state")
    if state not in {"paid", "failed"}:
        raise HTTPException(status_code=400, detail="Payment state is invalid.")
    invoice_reference = _one(values, "invoice_reference")
    payment_reference = _one(values, "payment_reference")
    if not invoice_reference or not payment_reference:
        raise HTTPException(status_code=400, detail="Invoice and payment/provider references are required.")
    status = RecurringServiceStatus.active if state == "paid" else RecurringServiceStatus.payment_blocked
    _save(request, identity, record, {"status": status, "invoice_reference": invoice_reference, "payment_reference": payment_reference, "last_payment_state": f"{state}: {invoice_reference} / {payment_reference}", "next_billing_date": _parse_date(_one(values, "next_billing_date"), "Next billing date") or record.next_billing_date, "next_action": "Continue recurring delivery." if state == "paid" else "Resolve failed/overdue recurring payment before further delivery."}, action="billing_paid" if state == "paid" else "billing_failed", reference=f"{invoice_reference} / {payment_reference}")
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/pause")
async def pause_recurring(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status is not RecurringServiceStatus.active:
        raise HTTPException(status_code=409, detail="Only active recurring service can be paused.")
    values = _values(await request.body())
    reference = _one(values, "reference")
    _save(request, identity, record, {"status": RecurringServiceStatus.paused, "pause_reference": reference, "next_action": "Resolve pause condition before recurring work resumes."}, action="service_paused", reference=reference)
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/resume")
async def resume_recurring(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status is not RecurringServiceStatus.paused:
        raise HTTPException(status_code=409, detail="Only paused recurring service can be resumed directly.")
    values = _values(await request.body())
    reference = _one(values, "reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Resume evidence/reference is required.")
    _save(request, identity, record, {"status": RecurringServiceStatus.active, "pause_reference": "", "next_action": "Continue recurring delivery and billing cadence."}, action="service_resumed", reference=reference)
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/renew")
async def renew_recurring(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status is not RecurringServiceStatus.active:
        raise HTTPException(status_code=409, detail="Only active recurring service can be renewed or re-scoped.")
    values = _values(await request.body())
    reference = _one(values, "renewal_reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Renewal/scope-price change reference is required.")
    try:
        version = RecurringServiceVersion(
            version=max((item.version for item in record.versions), default=0) + 1,
            scope=_lines(values, "scope"),
            deliverables=_lines(values, "deliverables"),
            exclusions=_lines(values, "exclusions"),
            cadence_description=_one(values, "cadence_description"),
            response_time=_one(values, "response_time"),
            escalation_expectations=_one(values, "escalation_expectations"),
            fee=_parse_money(_one(values, "fee")),
            currency=_one(values, "currency").upper(),
            billing_cadence=BillingCadence(_one(values, "billing_cadence")),
            effective_from=_parse_date(_one(values, "effective_from"), "Effective-from date"),
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Renewal version is invalid.") from exc
    _save(request, identity, record, {"versions": (*record.versions, version), "current_version": version.version, "renewal_reference": reference, "next_action": "Operate recurring service under the new approved plan version."}, action="service_renewed", reference=f"Version {version.version}: {reference}")
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/cancel-notice")
async def cancel_notice(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status not in {RecurringServiceStatus.active, RecurringServiceStatus.paused, RecurringServiceStatus.payment_blocked}:
        raise HTTPException(status_code=409, detail="Cancellation notice is not valid from the current recurring state.")
    values = _values(await request.body())
    reference = _one(values, "reference")
    _save(request, identity, record, {"status": RecurringServiceStatus.cancellation_pending, "cancellation_notice_date": _parse_date(_one(values, "notice_date"), "Cancellation notice date", required=True), "cancellation_effective_date": _parse_date(_one(values, "effective_date"), "Cancellation effective date"), "cancellation_reference": reference, "next_action": "Complete recurring-service exit and ownership/access handoff."}, action="cancellation_notice", reference=reference)
    return _redirect(project_id)


@router.post("/projects/{project_id}/recurring/cancel-complete")
async def cancel_complete(project_id: str, request: Request) -> RedirectResponse:
    identity, _customer_id, _customer, record = _record_for_write(request, project_id)
    if record.status is not RecurringServiceStatus.cancellation_pending:
        raise HTTPException(status_code=409, detail="Cancellation must be pending before it can be completed.")
    values = _values(await request.body())
    exit_reference = _one(values, "exit_handoff_reference")
    _save(request, identity, record, {"status": RecurringServiceStatus.cancelled, "cancellation_effective_date": _parse_date(_one(values, "effective_date"), "Cancellation effective date", required=True), "exit_handoff_reference": exit_reference, "next_action": "Recurring service closed; retain historical evidence only."}, action="service_cancelled", reference=exit_reference)
    return _redirect(project_id)
