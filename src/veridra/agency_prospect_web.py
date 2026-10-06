# ruff: noqa: E501
from __future__ import annotations

import html
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .agency_navigation import agency_navigation
from .collector import CollectionError
from .commercial_offer import INITIAL_IMPROVEMENT
from .core import Assessment, Status, UnsafeTargetError
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .outreach_suppression import TenantOutreachSuppressionStore
from .prospect import (
    OutreachMailboxType,
    Prospect,
    ProspectCommercialLossReason,
    ProspectDecision,
    ProspectRejectionReason,
    ProspectStatus,
    StageAQualification,
    discovery_signals_from_legacy_evidence,
    prospect_identifier,
)
from .prospect_activity import (
    ProspectActivityError,
    ProspectActivityType,
    TenantProspectActivityStore,
)
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy
from .service import assess_url
from .tenant_prospect_audit_store import (
    TenantProspectAuditStore,
    TenantProspectAuditStoreError,
)
from .tenant_prospect_store import TenantProspectStore, TenantProspectStoreError

router = APIRouter(prefix="/agency/prospects", tags=["agency-prospects"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1180px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.warning{border-left-color:#b7791f;background:#fff8e6}.success{border-left-color:#16794a;background:#f0faf5}.actions{display:flex;gap:8px;flex-wrap:wrap}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}label{display:block;font-weight:700;margin:12px 0 5px}input,textarea,select{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}textarea{min-height:100px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.score-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.timeline{list-style:none;padding:0;margin:0}.timeline li{padding:12px 0;border-bottom:1px solid #e5e7eb}.timeline time{display:block;color:#68707a;font-size:12px;margin-bottom:4px}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}.disclosure summary{cursor:pointer;font-size:18px;font-weight:700;list-style-position:outside}.disclosure[open] summary{margin-bottom:14px}.summary-note{font-size:13px;font-weight:400;color:#68707a;margin-left:8px}.toolbar{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px;align-items:end;margin:18px 0}.toolbar label{margin-top:0}.bulkbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0}.check{width:auto}.discovery{white-space:nowrap}.small{font-size:12px}.prospect-head{display:grid;grid-template-columns:2fr 1fr;gap:18px;align-items:start}.prospect-head h1{margin:0 0 8px}.prospect-meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 18px}.prospect-meta p{margin:0}.prospect-evidence{margin-top:12px}.workflow-section{margin-bottom:12px}.workflow-section>h2{margin-top:0}.compact-disclosure summary{font-size:16px}.compact-disclosure[open] summary{margin-bottom:12px}
.prospect-workbench{display:flex;flex-direction:column;gap:10px}.prospect-workbench>section{margin:0}.prospect-workbench .prospect-summary{padding:16px 18px}.prospect-workbench .prospect-head{gap:12px}.prospect-workbench .prospect-head h1{font-size:24px}.prospect-workbench .prospect-head p{margin:4px 0}.prospect-workbench .prospect-meta{grid-template-columns:repeat(4,minmax(0,1fr));gap:4px 14px;margin-top:8px}.prospect-workbench .prospect-evidence{margin:8px 0 0;padding:8px 10px;line-height:1.25;max-height:58px;overflow:auto}.prospect-workbench .qualification-panel{padding:14px 18px}.prospect-workbench .qualification-panel summary{font-size:16px}.prospect-workbench .qualification-panel[open] summary{margin-bottom:6px}.prospect-workbench .qualification-panel .muted{margin:4px 0 8px}.prospect-workbench .score-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:8px 10px}.prospect-workbench .score-grid label{margin:0 0 3px;font-size:12px}.prospect-workbench .score-grid select{padding:7px}.qualification-footer{display:grid;grid-template-columns:2fr 1fr auto;gap:10px;align-items:end;margin-top:8px}.qualification-footer label{margin:0 0 3px;font-size:12px}.qualification-footer textarea{min-height:54px;height:54px;resize:vertical}.qualification-footer select{padding:7px}.qualification-footer button{white-space:nowrap;margin:0}.stage-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.stage-strip .workflow-section{margin:0;padding:12px 14px;min-height:62px}.stage-strip .workflow-section h2{font-size:16px;margin:3px 0 6px}.stage-strip .workflow-section .notice{padding:7px 9px;margin:6px 0;font-size:12px}.stage-strip details summary{font-size:14px}.stage-strip details[open]{grid-column:1/-1}.stage-strip .timeline{max-height:220px;overflow:auto}
@media(min-width:1200px) and (min-height:800px){body{overflow:hidden}main{max-width:none;margin:18px 24px;padding:0;height:calc(100vh - 36px);overflow:hidden}.prospect-workbench{height:100%;overflow:hidden}.prospect-workbench .qualification-panel{flex:0 0 auto}.stage-strip{min-height:0}.stage-strip .workflow-section{overflow:auto;max-height:310px}}
@media(max-width:1199px){.prospect-workbench .score-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.qualification-footer{grid-template-columns:1fr 1fr}.qualification-footer button{grid-column:1/-1}.stage-strip{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:760px){body{overflow:auto}.row,.score-grid,.prospect-head,.prospect-meta,.prospect-workbench .score-grid,.prospect-workbench .prospect-meta,.qualification-footer,.stage-strip{grid-template-columns:1fr}main{height:auto;overflow:visible}.prospect-workbench{height:auto;overflow:visible}table{display:block;overflow:auto}}
"""

_COMMERCIAL_STATUSES = (
    ProspectStatus.contacted,
    ProspectStatus.responded,
    ProspectStatus.conversation,
    ProspectStatus.lost,
)
_TERMINAL_QUALIFICATION_STATUSES = {
    ProspectStatus.unsuitable,
    ProspectStatus.duplicate,
    ProspectStatus.archived,
}


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _activity_root(request: Request) -> Path:
    return _root(request) or Path.home() / ".veridra" / "tenants"


def _store(request: Request) -> TenantProspectStore:
    return TenantProspectStore(_root(request))


def _identity(request: Request) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_leads)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    return identity


def _configured_outreach_privacy_url() -> str:
    value = os.environ.get("VERIDRA_OUTREACH_PRIVACY_URL", "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return ""
    return value


def _named_professional_outreach_approval_reference() -> str:
    approved = os.environ.get(
        "VERIDRA_NAMED_PROFESSIONAL_OUTREACH_APPROVED",
        "",
    ).strip().casefold()
    reference = os.environ.get(
        "VERIDRA_NAMED_PROFESSIONAL_APPROVAL_REFERENCE",
        "",
    ).strip()
    if approved not in {"1", "true", "yes"} or not reference:
        return ""
    return reference


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Prospect workbench is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Prospect request is not permitted.") from exc


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _datetime_local(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat(timespec="minutes").replace("+00:00", "")


_OUTREACH_MARKET_BY_COUNTRY = {
    "IE": "Ireland",
    "ES": "Spain",
    "GB": "United Kingdom",
    "US": "United States",
    "CA": "Canada",
    "AU": "Australia",
    "NZ": "New Zealand",
}


_MANUAL_COUNTRY_NAME_TO_CODE = {
    "ireland": "IE",
    "spain": "ES",
    "united kingdom": "GB",
    "uk": "GB",
    "united states": "US",
    "usa": "US",
    "canada": "CA",
    "australia": "AU",
    "new zealand": "NZ",
}


def _manual_location_defaults(location: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in location.split(",") if part.strip()]
    locality = parts[0] if parts else ""
    country = _MANUAL_COUNTRY_NAME_TO_CODE.get(parts[-1].casefold(), "") if parts else ""
    return locality, locality, country


def _load(request: Request, identity: RequestIdentity, prospect_id: str) -> Prospect:
    store = _store(request)
    try:
        return store.load(identity, store.ref(identity, prospect_id))
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc


def _best_observation(assessment: Assessment) -> str:
    for finding in assessment.findings:
        if finding.status is Status.attention:
            return f"{finding.title}: {finding.summary}"[:1000]
    return "No material attention finding was observed in the bounded public assessment."


def _audit_summary(assessment: Assessment) -> str:
    return (
        f"{assessment.summary.get('attention', 0)} attention · "
        f"{assessment.summary.get('passed', 0)} passed · "
        f"{assessment.summary.get('unavailable', 0)} unavailable"
    )


def _display_sector(prospect: Prospect) -> str:
    if prospect.sector.strip():
        return prospect.sector.strip()
    folded = prospect.business_name.casefold()
    rules = (
        ("commissioner for oaths", "Commissioner for Oaths"),
        ("notary", "Notary public"),
        ("solicitor", "Solicitor"),
        ("law firm", "Law firm"),
        ("dentist", "Dentist"),
        ("dental", "Dentist"),
        ("physio", "Physiotherapist"),
        ("chiropr", "Chiropractor"),
        ("accountant", "Accountant"),
    )
    for token, label in rules:
        if token in folded:
            return label
    return "Unclassified"


def _decision(prospect: Prospect) -> str:
    if prospect.qualification is None:
        return "Not scored"
    return f"{prospect.qualification.score}/14 · {prospect.qualification.decision.value.replace('_', ' ')}"


def _commercial_status_options(prospect: Prospect) -> str:
    current = prospect.status
    return "".join(
        f"<option value='{item.value}'{' selected' if current is item else ''}>{item.value.replace('_', ' ').title()}</option>"
        for item in _COMMERCIAL_STATUSES
    )


def _commercial_loss_options(prospect: Prospect) -> str:
    current = prospect.commercial_loss_reason.value if prospect.commercial_loss_reason else ""
    return "<option value=''>None</option>" + "".join(
        f"<option value='{item.value}'{' selected' if current == item.value else ''}>{item.value.replace('_', ' ').title()}</option>"
        for item in ProspectCommercialLossReason
    )


@router.get("", response_class=HTMLResponse)
def prospect_index(request: Request) -> str:
    identity = _identity(request)
    entries = _store(request).list(identity)
    params = request.query_params

    status_filter = params.get("status", "").strip()
    sector_filter = params.get("sector", "").strip()
    territory_filter = params.get("territory", "").strip()
    qualification_filter = params.get("qualification", "").strip()
    website_filter = params.get("website", "").strip()
    sort_mode = params.get("sort", "updated-desc").strip()
    select_all = params.get("select", "") == "all"

    def signals_for(prospect: Prospect):  # type: ignore[no-untyped-def]
        return prospect.discovery or discovery_signals_from_legacy_evidence(
            prospect.evidence_summary
        )

    def include(prospect: Prospect) -> bool:
        if status_filter and prospect.status.value != status_filter:
            return False
        if sector_filter:
            actual_sector = _display_sector(prospect)
            if actual_sector.casefold() != sector_filter.casefold():
                return False
        if territory_filter:
            territory_values = {
                prospect.locality.casefold(),
                prospect.administrative_area.casefold(),
                prospect.country_code.casefold(),
            }
            if territory_filter.casefold() not in territory_values:
                return False
        if qualification_filter == "scored" and prospect.qualification is None:
            return False
        if qualification_filter == "not-scored" and prospect.qualification is not None:
            return False
        if website_filter == "with" and prospect.website is None:
            return False
        if website_filter == "without" and prospect.website is not None:
            return False
        return True

    entries = [(prospect_id, prospect) for prospect_id, prospect in entries if include(prospect)]

    if sort_mode == "discovery-desc":
        entries.sort(
            key=lambda item: (
                signals_for(item[1]).opportunity_score
                if signals_for(item[1]) is not None
                and signals_for(item[1]).opportunity_score is not None
                else -1,
                item[1].business_name.casefold(),
            ),
            reverse=True,
        )
    elif sort_mode == "qualification-desc":
        entries.sort(
            key=lambda item: (
                item[1].qualification.score if item[1].qualification is not None else -1,
                item[1].business_name.casefold(),
            ),
            reverse=True,
        )
    elif sort_mode == "business-asc":
        entries.sort(key=lambda item: item[1].business_name.casefold())
    elif sort_mode == "sector-asc":
        entries.sort(key=lambda item: (_display_sector(item[1]).casefold(), item[1].business_name.casefold()))
    elif sort_mode == "territory-asc":
        entries.sort(key=lambda item: (item[1].locality.casefold(), item[1].business_name.casefold()))
    elif sort_mode == "status-asc":
        entries.sort(key=lambda item: (item[1].status.value, item[1].business_name.casefold()))
    elif sort_mode == "followup-asc":
        entries.sort(
            key=lambda item: (
                item[1].next_follow_up_at or datetime.max.replace(tzinfo=UTC),
                item[1].business_name.casefold(),
            )
        )
    else:
        sort_mode = "updated-desc"
        entries.sort(key=lambda item: (item[1].updated_at, item[0]), reverse=True)

    all_entries = _store(request).list(identity)
    sectors = sorted({_display_sector(prospect) for _, prospect in all_entries})
    territories = sorted(
        {
            prospect.locality
            for _, prospect in all_entries
            if prospect.locality
        }
    )

    def option(value: str, label: str, current: str) -> str:
        return f"<option value='{html.escape(value, quote=True)}'{' selected' if current == value else ''}>{html.escape(label)}</option>"

    status_options = "<option value=''>All statuses</option>" + "".join(
        option(item.value, item.value.replace("_", " ").title(), status_filter)
        for item in ProspectStatus
    )
    sector_options = "<option value=''>All sectors</option>" + "".join(
        option(item, item, sector_filter) for item in sectors
    )
    territory_options = "<option value=''>All territories</option>" + "".join(
        option(item, item, territory_filter) for item in territories
    )
    qualification_options = (
        option("", "All qualification", qualification_filter)
        + option("scored", "Scored", qualification_filter)
        + option("not-scored", "Not scored", qualification_filter)
    )
    website_options = (
        option("", "All websites", website_filter)
        + option("with", "With website", website_filter)
        + option("without", "No website", website_filter)
    )
    sort_options = "".join(
        option(value, label, sort_mode)
        for value, label in (
            ("updated-desc", "Recently updated"),
            ("discovery-desc", "Discovery opportunity — highest"),
            ("qualification-desc", "Qualification — highest"),
            ("business-asc", "Business — A to Z"),
            ("sector-asc", "Sector — A to Z"),
            ("territory-asc", "Territory — A to Z"),
            ("status-asc", "Status"),
            ("followup-asc", "Follow-up — soonest"),
        )
    )

    preserved = {
        "status": status_filter,
        "sector": sector_filter,
        "territory": territory_filter,
        "qualification": qualification_filter,
        "website": website_filter,
        "sort": sort_mode,
    }
    select_query = urlencode(
        {
            **{key: value for key, value in preserved.items() if value},
            "select": "none" if select_all else "all",
        }
    )

    rows: list[str] = []
    for prospect_id, prospect in entries:
        website = str(prospect.website) if prospect.website is not None else "—"
        follow_up = prospect.next_follow_up_at.isoformat() if prospect.next_follow_up_at else "—"
        discovery = signals_for(prospect)
        discovery_text = "Not captured"
        if discovery is not None and discovery.opportunity_score is not None:
            rank_text = f" · Maps #{discovery.result_rank}" if discovery.result_rank else ""
            discovery_text = (
                f"{discovery.opportunity_band.upper()} {discovery.opportunity_score}/100"
                f"{rank_text}"
            )
        checked = " checked" if select_all else ""
        rows.append(
            "<tr>"
            f"<td><input class='check' type='checkbox' name='selected_id' value='{html.escape(prospect_id, quote=True)}'{checked}></td>"
            f"<td><strong>{html.escape(prospect.business_name)}</strong><br><span class='muted'>{html.escape(prospect.sector or 'Unclassified')}</span></td>"
            f"<td>{html.escape(prospect.locality or '—')}<br><span class='muted'>{html.escape(prospect.administrative_area or '')}</span></td>"
            f"<td>{html.escape(website)}</td>"
            f"<td class='discovery'>{html.escape(discovery_text)}</td>"
            f"<td><span class='badge'>{html.escape(prospect.status.value)}</span></td>"
            f"<td>{html.escape(follow_up)}<br><span class='muted'>{html.escape(prospect.next_action or 'No action')}</span></td>"
            f"<td>{html.escape(_decision(prospect))}</td>"
            f"<td><div class='actions'><a class='button' href='/agency/prospects/{html.escape(prospect_id, quote=True)}'>Review</a></div></td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr><th>Keep</th><th>Business</th><th>Territory</th><th>Website</th><th>Discovery</th><th>Status</th><th>Follow-up</th><th>Qualification</th><th>Actions</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else "<p class='notice'>No prospects match the current filters.</p>"
    )

    navigation = agency_navigation(identity, current="prospects")
    body = f"""{navigation}<div class='agency-workbench'>
    <section class='workbench-head'>
      <div class='actions'><a class='button' href='/agency/prospects/new'>Add prospect</a><a class='button secondary' href='/agency/prospects/discover'>Find prospects</a></div>
      <h1>Prospects</h1>
      <p class='muted'>Businesses discovered for possible website improvement work. Discovery opportunity is preserved separately from human qualification; the machine score never approves outreach.</p>
      <form method='get' action='/agency/prospects'>
        <div class='toolbar'>
          <div><label for='status'>Status</label><select id='status' name='status'>{status_options}</select></div>
          <div><label for='sector'>Sector</label><select id='sector' name='sector'>{sector_options}</select></div>
          <div><label for='territory'>Territory</label><select id='territory' name='territory'>{territory_options}</select></div>
          <div><label for='qualification'>Qualification</label><select id='qualification' name='qualification'>{qualification_options}</select></div>
          <div><label for='website_filter'>Website</label><select id='website_filter' name='website'>{website_options}</select></div>
          <div><label for='sort'>Sort</label><select id='sort' name='sort'>{sort_options}</select></div>
        </div>
        <div class='actions'><button type='submit'>Apply filters</button><a class='button secondary' href='/agency/prospects'>Reset</a><span class='muted'><strong>{len(entries)}</strong> prospects shown</span></div>
      </form>
    </section>
    <section class='workbench-body'><div class='workbench-scroll'>
      <form method='post' action='/agency/prospects/bulk/prepare-review'>
        <div class='bulkbar'>
          <a class='button secondary' href='/agency/prospects?{select_query}'>{'Clear all' if select_all else 'Select all'}</a>
          <button type='submit'>Prepare selected for review</button>
          <span class='muted small'>This does not qualify or approve outreach; it only sets the next operator action.</span>
        </div>
        {table}
      </form>
    </div></section></div>"""
    return _page("Webify prospects", body)


@router.post("/bulk/prepare-review", response_model=None)
async def prepare_selected_prospects(request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    selected_ids = [value for value in values.get("selected_id", []) if value]
    if not selected_ids:
        raise HTTPException(status_code=400, detail="Select at least one prospect.")

    store = _store(request)
    now = datetime.now(UTC)
    for prospect_id in selected_ids:
        try:
            prospect = store.load(identity, store.ref(identity, prospect_id))
        except TenantProspectStoreError:
            continue
        if prospect.status is not ProspectStatus.needs_review or prospect.qualification is not None:
            continue
        updated = Prospect.model_validate(
            {
                **prospect.model_dump(mode="json"),
                "next_action": prospect.next_action or "Complete Stage A qualification review",
                "updated_at": now,
            }
        )
        store.replace(identity, store.ref(identity, prospect_id), updated)
    return RedirectResponse("/agency/prospects?status=needs_review&qualification=not-scored", status_code=303)


@router.get("/new", response_class=HTMLResponse)
def new_prospect_page(request: Request) -> str:
    identity = _identity(request)
    navigation = agency_navigation(identity, current="prospects")
    body = f"""{navigation}<section><h1>Add prospect</h1>
    <p class='muted'>Use this only when you already found a business outside VERIDRA Discovery.</p>
    <form method='post' action='/agency/prospects/new'>
      <div class='row'><div><label for='business_name'>Business name</label><input id='business_name' name='business_name' maxlength='200' required></div>
      <div><label for='website'>Website</label><input id='website' name='website' maxlength='2048' placeholder='https://example.com'></div></div>
      <div class='row'><div><label for='sector'>Business type</label><input id='sector' name='sector' maxlength='120' placeholder='Dentist, lawyer, physiotherapist…'></div>
      <div><label for='location'>Location</label><input id='location' name='location' maxlength='160' placeholder='Dublin, Ireland'></div></div>
      <div class='row'><div><label for='contact_email'>Contact email</label><input id='contact_email' name='contact_email' type='email' maxlength='254'></div>
      <div><label for='phone'>Phone</label><input id='phone' name='phone' maxlength='80'></div></div>
      <details class='disclosure'><summary>Advanced location override</summary>
        <div class='row'><div><label for='locality'>Locality</label><input id='locality' name='locality' maxlength='120' placeholder='Auto from Location'></div>
        <div><label for='administrative_area'>Administrative area</label><input id='administrative_area' name='administrative_area' maxlength='120' placeholder='Auto from Location'></div></div>
        <label for='country_code'>Country code</label><input id='country_code' name='country_code' maxlength='2' placeholder='Auto'>
      </details>
      <label for='evidence_summary'>Why is this business worth reviewing?</label>
      <textarea id='evidence_summary' name='evidence_summary' maxlength='4000' placeholder='Source and useful discovery evidence.'></textarea>
      <button type='submit'>Create prospect</button>
    </form></section>"""
    return _page("Add prospect", body)


@router.post("/new", response_model=None)
async def create_prospect(request: Request) -> HTMLResponse | RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    location = _one(values, "location")
    auto_locality, auto_area, auto_country = _manual_location_defaults(location)
    try:
        prospect = Prospect.model_validate(
            {
                "business_name": _one(values, "business_name"),
                "website": _one(values, "website") or None,
                "sector": _one(values, "sector"),
                "locality": _one(values, "locality") or auto_locality,
                "administrative_area": _one(values, "administrative_area") or auto_area,
                "country_code": (_one(values, "country_code") or auto_country).upper(),
                "phone": _one(values, "phone"),
                "contact_email": _one(values, "contact_email"),
                "provider": "manual",
                "provider_key": "",
                "evidence_summary": _one(values, "evidence_summary"),
                "status": ProspectStatus.needs_review,
            }
        )
    except ValidationError as exc:
        return HTMLResponse(
            _page(
                "Invalid prospect",
                f"<section><h1>Prospect could not be saved</h1><p class='muted'>{html.escape(str(exc))}</p><p><a href='/agency/prospects/new'>Return to form</a></p></section>",
            ),
            status_code=400,
        )
    prospect_id = prospect_identifier(prospect)
    store = _store(request)
    try:
        store.load(identity, store.ref(identity, prospect_id))
    except TenantProspectStoreError:
        store.save(identity, prospect)
    else:
        return HTMLResponse(
            _page(
                "Duplicate prospect",
                "<section><h1>Prospect already exists</h1><p class='muted'>Review the existing record instead of replacing its qualification or outreach state.</p><p><a href='/agency/prospects'>Return to prospects</a></p></section>",
            )
        )
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)


@router.get("/{prospect_id}", response_class=HTMLResponse)
def prospect_detail(prospect_id: str, request: Request) -> str:
    identity = _identity(request)
    prospect = _load(request, identity, prospect_id)
    navigation = agency_navigation(identity, current="prospects")
    website = str(prospect.website) if prospect.website is not None else "—"

    audit_store = TenantProspectAuditStore(_root(request))
    try:
        audit_entries = audit_store.list(identity, prospect_id)
    except TenantProspectAuditStoreError:
        audit_entries = []
    latest_audit = None
    if audit_entries:
        try:
            latest_audit = audit_store.load(
                identity,
                audit_store.ref(identity, prospect_id, audit_entries[0].id),
            )
        except TenantProspectAuditStoreError:
            latest_audit = None

    try:
        events = TenantProspectActivityStore(_activity_root(request)).list(identity, prospect_id)
    except ProspectActivityError as exc:
        raise HTTPException(status_code=404, detail="Prospect activity could not be read.") from exc
    timeline = "".join(
        f"<li><time>{html.escape(event.occurred_at.isoformat())}</time><strong>{html.escape(event.event_type.value.replace('_', ' ').title())}</strong><div>{html.escape(event.summary)}</div></li>"
        for event in reversed(events)
    ) or "<li class='muted'>No activity recorded yet.</li>"

    qualification = prospect.qualification
    values = {
        "active_real_business": qualification.active_real_business if qualification else 0,
        "website_commercial_importance": qualification.website_commercial_importance if qualification else 0,
        "business_economic_value": qualification.business_economic_value if qualification else 0,
        "business_size_fit": qualification.business_size_fit if qualification else 0,
        "decision_maker_reachability": qualification.decision_maker_reachability if qualification else 0,
        "website_manageability": qualification.website_manageability if qualification else 0,
        "no_existing_web_team": qualification.no_existing_web_team if qualification else 0,
    }
    score_options = (
        (0, "0 — Not demonstrated"),
        (1, "1 — Partial / uncertain evidence"),
        (2, "2 — Clear evidence"),
    )
    score_fields = "".join(
        f"<div><label for='{name}'>{html.escape(label)}</label>"
        f"<p class='muted small'>{html.escape(guidance)}</p>"
        f"<select id='{name}' name='{name}' aria-describedby='{name}-guidance'>"
        + "".join(
            f"<option value='{value}'{' selected' if selected == value else ''}>{html.escape(option_label)}</option>"
            for value, option_label in score_options
        )
        + "</select>"
        f"<span id='{name}-guidance' class='muted small'>Use only observed or documented evidence; do not infer missing facts.</span></div>"
        for name, label, guidance, selected in (
            (
                "active_real_business",
                "Active real business",
                "Evidence the organisation is currently operating: current business listing, recent reviews, opening hours or other public activity.",
                values["active_real_business"],
            ),
            (
                "website_commercial_importance",
                "Website matters commercially",
                "Evidence the website supports enquiries, bookings, trust, directions, service discovery or another meaningful customer action.",
                values["website_commercial_importance"],
            ),
            (
                "business_economic_value",
                "Likely value of improvement",
                "Evidence the business sells meaningful services or products where better digital presence could reasonably matter; avoid guessing revenue.",
                values["business_economic_value"],
            ),
            (
                "business_size_fit",
                "Fit for Webify",
                "Evidence the business appears small enough for Webify to serve directly and substantial enough to justify professional improvement work.",
                values["business_size_fit"],
            ),
            (
                "decision_maker_reachability",
                "Decision-maker reachability",
                "Evidence a legitimate business contact route or identifiable decision-maker path exists. Do not treat private-person contact data as a positive signal.",
                values["decision_maker_reachability"],
            ),
            (
                "website_manageability",
                "Website looks manageable",
                "Evidence the public site appears within Webify's practical delivery scope rather than requiring a large custom platform or specialist engineering team.",
                values["website_manageability"],
            ),
            (
                "no_existing_web_team",
                "No obvious existing web team",
                "Evidence does not show an active agency or internal web team already handling the same work. Unknown should stay partial/uncertain, not be assumed.",
                values["no_existing_web_team"],
            ),
        )
    )
    reason = qualification.reason if qualification else ""
    current_rejection = prospect.rejection_reason.value if prospect.rejection_reason else ""
    rejection_options = "<option value=''>None</option>" + "".join(
        f"<option value='{item.value}'{' selected' if current_rejection == item.value else ''}>{item.value.replace('_', ' ').title()}</option>"
        for item in ProspectRejectionReason
    )
    qualification_open = " open" if qualification is None else ""
    qualification_section = f"<section class='workflow-section'><details class='disclosure compact-disclosure qualification-panel'{qualification_open}><summary>Qualification <span class='summary-note'>Step 1 · {html.escape(_decision(prospect))}</span></summary><p class='muted'>Score from the evidence already recorded for this prospect: 0 = not demonstrated, 1 = partial or uncertain, 2 = clear evidence. 11–14 unlocks audit · 8–10 hold · lower scores need more evidence or rejection. Unknown facts must not be upgraded by assumption.</p><form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/qualify'><div class='score-grid'>{score_fields}</div><div class='qualification-footer'><div><label>Why this score?</label><textarea name='reason' maxlength='1000' required>{html.escape(reason)}</textarea></div><div><label>Rejection reason (optional)</label><select name='rejection_reason'>{rejection_options}</select></div><button type='submit'>Save qualification</button></div></form></details></section>"

    if prospect.website is None:
        audit_section = "<section class='workflow-section'><span class='muted small'>Step 2</span><h2>Prospect audit</h2><p class='notice'>No public website is recorded. This prospect can still be commercially qualified, but website audit evidence is not available.</p></section>"
    elif qualification is None or qualification.decision is not ProspectDecision.send_to_audit:
        audit_section = "<section class='workflow-section'><span class='muted small'>Step 2</span><h2>Prospect audit</h2><p class='notice warning'>Complete qualification with an audit-ready decision before spending time on a website audit.</p></section>"
    else:
        audit_button = (
            f"<form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/audit'><button type='submit'>{'Re-run prospect audit' if latest_audit else 'Run prospect audit'}</button></form>"
            if prospect.status in {ProspectStatus.ready_for_audit, ProspectStatus.audited}
            else ""
        )
        if latest_audit is None:
            audit_detail = "<p class='muted'>No prospect-scoped assessment has been saved yet.</p>"
        else:
            findings = "".join(
                f"<li><strong>{html.escape(item.title)}</strong> — {html.escape(item.summary)}</li>"
                for item in latest_audit.findings
                if item.status is Status.attention
            ) or "<li>No attention findings observed.</li>"
            fixable_value = "" if prospect.webify_fixable is None else ("yes" if prospect.webify_fixable else "no")
            audit_detail = f"""
            <p><strong>Latest audit:</strong> {html.escape(latest_audit.generated_at.isoformat())}<br>
            <strong>Evidence:</strong> {html.escape(_audit_summary(latest_audit))}</p>
            <ul>{findings}</ul>
            <form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/audit/review'>
              <label>Best business-facing observation</label>
              <textarea name='best_observation' maxlength='1000' required>{html.escape(prospect.best_observation or _best_observation(latest_audit))}</textarea>
              <div class='row'><div><label>Can Webify safely improve it?</label><select name='webify_fixable' required>
                <option value=''{' selected' if not fixable_value else ''}>Review required</option>
                <option value='yes'{' selected' if fixable_value == 'yes' else ''}>Yes</option>
                <option value='no'{' selected' if fixable_value == 'no' else ''}>No</option>
              </select></div><div><label>Estimated effort (hours)</label><input name='estimated_effort_hours' type='number' min='0' max='10000' step='0.25' value='{"" if prospect.estimated_effort_hours is None else prospect.estimated_effort_hours}'></div></div>
              <label>Likely offer</label><input name='likely_offer' maxlength='240' value='{html.escape(prospect.likely_offer or INITIAL_IMPROVEMENT.title, quote=True)}'>
              <button type='submit'>Save audit review</button>
            </form>"""
        audit_section = f"<section class='workflow-section'><span class='muted small'>Step 2</span><h2>Prospect audit</h2><p class='muted'>This evidence belongs to the prospect. It does not create a customer or client project.</p>{audit_button}{audit_detail}</section>"

    mailbox_options = "".join(
        f"<option value='{item.value}'{' selected' if prospect.outreach_mailbox_type is item else ''}>{item.value.replace('_', ' ').title()}</option>"
        for item in OutreachMailboxType
    )
    compliance_ready = (
        prospect.audit_assessment_id
        and prospect.webify_fixable is True
        and prospect.outreach_eligible
        and prospect.status in {
            ProspectStatus.approved_for_outreach,
            ProspectStatus.contacted,
            ProspectStatus.responded,
            ProspectStatus.conversation,
            ProspectStatus.proposal,
            ProspectStatus.customer,
        }
    )
    compliance_state = "APPROVED" if compliance_ready else "NOT APPROVED"
    privacy_url = _configured_outreach_privacy_url()
    named_professional_approval = _named_professional_outreach_approval_reference()
    privacy_url_status = (
        f"<a href='{html.escape(privacy_url, quote=True)}' target='_blank' rel='noopener'>"
        "Open configured Webify Privacy Notice</a>"
        if privacy_url
        else "<span class='warning'>No valid VERIDRA_OUTREACH_PRIVACY_URL is configured.</span>"
    )
    named_professional_status = (
        f"<span class='success'>Qualified approval recorded: {html.escape(named_professional_approval)}</span>"
        if named_professional_approval
        else "<span class='warning'>Named-professional first contact is blocked pending qualified legal approval.</span>"
    )
    outreach_section = f"""<section class='workflow-section'><details class='disclosure compact-disclosure'><summary>3. Outreach eligibility <span class='summary-note'>{compliance_state}</span></summary>
    <p class='notice {'success' if compliance_ready else 'warning'}'><strong>{compliance_state}</strong> — commercial score never overrides this compliance gate.</p>
    <p><strong>Privacy Notice:</strong> {privacy_url_status}</p>
    <p><strong>Named-professional legal gate:</strong> {named_professional_status}</p>
    <form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/outreach-review'>
      <div class='row'><div><label>Market</label><input name='outreach_market' maxlength='80' value='{html.escape(prospect.outreach_market or _OUTREACH_MARKET_BY_COUNTRY.get(prospect.country_code, prospect.country_code), quote=True)}' required></div>
      <div><label>Mailbox type</label><select name='outreach_mailbox_type'>{mailbox_options}</select></div></div>
      <label>Contact source / evidence</label><input name='contact_source' maxlength='240' value='{html.escape(prospect.contact_source, quote=True)}' placeholder='Business website, Google Business Profile, professional directory…' required>
      <label>Source URL (optional)</label><input name='contact_source_url' maxlength='2048' value='{html.escape(prospect.contact_source_url, quote=True)}'>
      <div class='row'><div><label>Named contact role (required for named-person mailbox)</label><input name='named_contact_role' maxlength='160' value='{html.escape(prospect.named_contact_role, quote=True)}'></div>
      <div><label>Why is the offer relevant to that role?</label><input name='role_relevance_basis' maxlength='1000' value='{html.escape(prospect.role_relevance_basis, quote=True)}'></div></div>
      <label><input type='checkbox' name='privacy_notice_ready' value='yes' {'checked' if prospect.privacy_notice_ready else ''}> Webify Privacy Notice is ready to be provided/linked in the first communication</label>
      <label><input type='checkbox' name='suppression_checked' value='yes'> Suppression / prior objection checked now</label>
      <label><input type='checkbox' name='objection_received' value='yes'> A prior objection / do-not-contact request exists</label>
      <label>If not eligible, reason</label><textarea name='outreach_ineligible_reason' maxlength='1000'>{html.escape(prospect.outreach_ineligible_reason)}</textarea>
      <button type='submit'>Review outreach eligibility</button>
    </form></details></section>"""

    if prospect.status in _TERMINAL_QUALIFICATION_STATUSES:
        commercial_section = "<section id='commercial-funnel' class='workflow-section'><details class='disclosure compact-disclosure'><summary>4. Commercial progress <span class='summary-note'>Locked</span></summary><p class='notice warning'>This prospect is rejected/archived and cannot enter the sales workflow.</p></details></section>"
    elif prospect.status not in {
        ProspectStatus.approved_for_outreach,
        ProspectStatus.contacted,
        ProspectStatus.responded,
        ProspectStatus.conversation,
        ProspectStatus.proposal,
        ProspectStatus.customer,
        ProspectStatus.lost,
    }:
        commercial_section = "<section id='commercial-funnel' class='workflow-section'><details class='disclosure compact-disclosure'><summary>4. Commercial progress <span class='summary-note'>Locked</span></summary><p class='notice warning'>Sales/outreach progression remains locked until the prospect audit and outreach eligibility gates are satisfied.</p></details></section>"
    else:
        commercial_section = f"<section id='commercial-funnel' class='workflow-section'><details class='disclosure compact-disclosure'><summary>4. Commercial progress <span class='summary-note'>{html.escape(prospect.status.value.replace('_', ' '))}</span></summary><p class='muted'>Record what actually happened after outreach approval. VERIDRA records the outcome; it does not send the message.</p><form method='post' action='/agency/prospects/{html.escape(prospect_id, quote=True)}/commercial'><div class='row'><div><label for='commercial_status'>Funnel stage</label><select id='commercial_status' name='status'>{_commercial_status_options(prospect)}</select></div><div><label for='commercial_loss_reason'>Loss reason</label><select id='commercial_loss_reason' name='commercial_loss_reason'>{_commercial_loss_options(prospect)}</select></div></div><div class='row'><div><label for='outreach_offer'>Offer used</label><input id='outreach_offer' name='outreach_offer' maxlength='240' value='{html.escape(prospect.outreach_offer or prospect.likely_offer, quote=True)}'></div><div><label for='message_variant'>Message variant / cohort</label><input id='message_variant' name='message_variant' maxlength='120' value='{html.escape(prospect.message_variant, quote=True)}'></div><div><label for='last_contacted_at'>Last contacted</label><input id='last_contacted_at' name='last_contacted_at' type='datetime-local' value='{html.escape(_datetime_local(prospect.last_contacted_at), quote=True)}'></div><div><label for='next_follow_up_at'>Next follow-up</label><input id='next_follow_up_at' name='next_follow_up_at' type='datetime-local' value='{html.escape(_datetime_local(prospect.next_follow_up_at), quote=True)}'></div></div><label><input type='checkbox' name='first_touch_compliance_confirmed' value='yes'> For first contact: Webify is identified, the Privacy Notice is provided/linked, a valid reply/contact route is present, and an easy objection/opt-out path is included</label><label for='next_action'>Next action</label><input id='next_action' name='next_action' maxlength='500' value='{html.escape(prospect.next_action, quote=True)}'><label for='commercial_note'>Commercial note</label><textarea id='commercial_note' name='commercial_note' maxlength='2000'>{html.escape(prospect.commercial_note)}</textarea><button type='submit'>Save commercial progress</button></form></details></section>"

    activity_section = f"<section class='workflow-section'><details class='disclosure compact-disclosure'><summary>5. Activity history <span class='summary-note'>{len(events)} event{'s' if len(events) != 1 else ''}</span></summary><ul class='timeline'>{timeline}</ul></details></section>"
    body = f"{navigation}<div class='prospect-workbench'><section class='prospect-summary'><div class='prospect-head'><div><h1>{html.escape(prospect.business_name)}</h1><p><span class='badge'>{html.escape(prospect.status.value.replace('_', ' '))}</span> · Qualification: {html.escape(_decision(prospect))}</p></div><div><strong>Next action</strong><br><span class='muted'>{html.escape(prospect.next_action or 'Complete qualification')}</span></div></div><div class='prospect-meta'><p><strong>Website</strong><br>{html.escape(website)}</p><p><strong>Sector</strong><br>{html.escape(prospect.sector or '—')}</p><p><strong>Territory</strong><br>{html.escape(prospect.locality or '—')}, {html.escape(prospect.administrative_area or '—')}</p><p><strong>Contact</strong><br>{html.escape(prospect.contact_email or prospect.phone or '—')}</p></div><p class='notice prospect-evidence'>{html.escape(prospect.evidence_summary or 'No discovery evidence recorded yet.')}</p></section>{qualification_section}<div class='stage-strip'>{audit_section}{outreach_section}{commercial_section}{activity_section}</div></div>"
    return _page(prospect.business_name, body)


@router.post("/{prospect_id}/audit")
def run_prospect_audit(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    prospect = _load(request, identity, prospect_id)
    if prospect.website is None:
        raise HTTPException(status_code=409, detail="A website is required for a prospect audit.")
    if prospect.qualification is None or prospect.qualification.decision is not ProspectDecision.send_to_audit:
        raise HTTPException(status_code=409, detail="Prospect qualification must be audit-ready first.")
    if prospect.status not in {ProspectStatus.ready_for_audit, ProspectStatus.audited}:
        raise HTTPException(status_code=409, detail="Prospect audit is not available in the current lifecycle state.")
    try:
        assessment = assess_url(str(prospect.website))
        assessment_id = TenantProspectAuditStore(_root(request)).save(
            identity, prospect_id, assessment
        )
    except (UnsafeTargetError, CollectionError, TenantProspectAuditStoreError) as exc:
        raise HTTPException(status_code=400, detail=f"Prospect audit could not be completed: {exc}") from exc
    now = datetime.now(UTC)
    updated = Prospect.model_validate(
        {
            **prospect.model_dump(mode="json"),
            "audit_assessment_id": assessment_id,
            "audited_at": now,
            "best_observation": prospect.best_observation or _best_observation(assessment),
            "likely_offer": prospect.likely_offer or INITIAL_IMPROVEMENT.title,
            "status": ProspectStatus.audited,
            "next_action": "Review audit evidence and outreach eligibility",
            "updated_at": now,
        }
    )
    store = _store(request)
    store.replace(identity, store.ref(identity, prospect_id), updated)
    TenantProspectActivityStore(_activity_root(request)).append(
        identity,
        prospect_id,
        ProspectActivityType.audit_completed,
        f"Prospect website audit saved as {assessment_id}",
        metadata={"assessment_id": assessment_id},
    )
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)


@router.post("/{prospect_id}/audit/review")
async def review_prospect_audit(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    prospect = _load(request, identity, prospect_id)
    if not prospect.audit_assessment_id or prospect.status not in {ProspectStatus.audited, ProspectStatus.approved_for_outreach}:
        raise HTTPException(status_code=409, detail="Run and save a prospect audit before reviewing it.")
    values = _values(await request.body())
    fixable_raw = _one(values, "webify_fixable")
    if fixable_raw not in {"yes", "no"}:
        raise HTTPException(status_code=400, detail="Choose whether Webify can safely improve the observed issue.")
    effort_raw = _one(values, "estimated_effort_hours")
    try:
        effort = float(effort_raw) if effort_raw else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Estimated effort must be numeric.") from exc
    now = datetime.now(UTC)
    updated = Prospect.model_validate(
        {
            **prospect.model_dump(mode="json"),
            "best_observation": _one(values, "best_observation"),
            "webify_fixable": fixable_raw == "yes",
            "estimated_effort_hours": effort,
            "likely_offer": _one(values, "likely_offer"),
            "next_action": (
                "Complete outreach eligibility review"
                if fixable_raw == "yes"
                else "Hold or reject: no safe Webify fix identified"
            ),
            "updated_at": now,
        }
    )
    store = _store(request)
    store.replace(identity, store.ref(identity, prospect_id), updated)
    TenantProspectActivityStore(_activity_root(request)).append(
        identity,
        prospect_id,
        ProspectActivityType.audit_reviewed,
        "Prospect audit evidence reviewed by operator",
    )
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)


@router.post("/{prospect_id}/outreach-review")
async def review_outreach_eligibility(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    prospect = _load(request, identity, prospect_id)
    if prospect.status is not ProspectStatus.audited or not prospect.audit_assessment_id:
        raise HTTPException(status_code=409, detail="A persisted prospect audit is required before outreach review.")
    if prospect.webify_fixable is not True:
        raise HTTPException(status_code=409, detail="A safe, Webify-fixable opportunity must be confirmed before outreach review.")
    if not prospect.contact_email:
        raise HTTPException(status_code=409, detail="A contact email is required before email outreach can be approved.")
    values = _values(await request.body())
    try:
        mailbox = OutreachMailboxType(_one(values, "outreach_mailbox_type"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Mailbox type is invalid.") from exc
    source = _one(values, "contact_source")
    market = _one(values, "outreach_market")
    role = _one(values, "named_contact_role")
    relevance = _one(values, "role_relevance_basis")
    privacy_ready = _one(values, "privacy_notice_ready") == "yes"
    suppression_checked = _one(values, "suppression_checked") == "yes"
    objection_received = _one(values, "objection_received") == "yes"

    reasons: list[str] = []
    if not market:
        reasons.append("Market/jurisdiction is not recorded.")
    if not source:
        reasons.append("Contact source evidence is missing.")
    if mailbox in {OutreachMailboxType.unknown, OutreachMailboxType.personal_unverified}:
        reasons.append("Mailbox is not eligible for the approved Ireland-first B2B workflow.")
    if mailbox is OutreachMailboxType.named_professional:
        if not role or not relevance:
            reasons.append("Named professional mailbox requires role and role-relevance evidence.")
        if not _named_professional_outreach_approval_reference():
            reasons.append(
                "Named professional outreach remains blocked pending explicit qualified legal approval."
            )
    privacy_url = _configured_outreach_privacy_url()
    if not privacy_url:
        reasons.append("A public HTTPS Webify Privacy Notice URL is not configured.")
    if not privacy_ready:
        reasons.append("Privacy Notice is not ready for first-touch transparency.")
    if not suppression_checked:
        reasons.append("Suppression/prior-objection check was not confirmed.")
    suppression_store = TenantOutreachSuppressionStore(_root(request))
    existing_suppression = suppression_store.load(identity, prospect.contact_email)
    if objection_received or prospect.objection_received_at is not None:
        if existing_suppression is None:
            suppression_store.suppress(
                identity,
                email=prospect.contact_email,
                reason="Direct-marketing objection / do-not-contact instruction",
                source_prospect_id=prospect_id,
            )
        reasons.append("A prior objection/do-not-contact instruction exists.")
    elif existing_suppression is not None:
        reasons.append("Contact email is present in the tenant suppression register.")

    operator_reason = _one(values, "outreach_ineligible_reason")
    if operator_reason:
        reasons.append(operator_reason)
    eligible = not reasons
    now = datetime.now(UTC)
    updated = Prospect.model_validate(
        {
            **prospect.model_dump(mode="json"),
            "outreach_market": market,
            "outreach_mailbox_type": mailbox.value,
            "contact_source": source,
            "contact_source_url": _one(values, "contact_source_url"),
            "named_contact_role": role,
            "role_relevance_basis": relevance,
            "privacy_notice_ready": privacy_ready,
            "privacy_notice_url": privacy_url if privacy_ready else prospect.privacy_notice_url,
            "suppression_checked_at": now if suppression_checked else prospect.suppression_checked_at,
            "outreach_eligible": eligible,
            "outreach_ineligible_reason": "; ".join(reasons),
            "outreach_reviewed_at": now,
            "objection_received_at": now if objection_received else prospect.objection_received_at,
            "status": ProspectStatus.approved_for_outreach if eligible else ProspectStatus.audited,
            "next_action": (
                "Prepare one compliant first-touch message; sending remains an explicit operator action"
                if eligible
                else "Resolve outreach compliance blockers before contact"
            ),
            "updated_at": now,
        }
    )
    store = _store(request)
    store.replace(identity, store.ref(identity, prospect_id), updated)
    TenantProspectActivityStore(_activity_root(request)).append(
        identity,
        prospect_id,
        ProspectActivityType.outreach_reviewed,
        "Outreach eligibility approved" if eligible else "Outreach eligibility blocked",
        metadata={"eligible": str(eligible).lower()},
    )
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)


@router.post("/{prospect_id}/qualify")
async def qualify_prospect(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    prospect = _load(request, identity, prospect_id)
    values = _values(await request.body())
    try:
        rejection_raw = _one(values, "rejection_reason")
        rejection = ProspectRejectionReason(rejection_raw) if rejection_raw else None
        qualification = StageAQualification(
            active_real_business=int(_one(values, "active_real_business")),
            website_commercial_importance=int(_one(values, "website_commercial_importance")),
            business_economic_value=int(_one(values, "business_economic_value")),
            business_size_fit=int(_one(values, "business_size_fit")),
            decision_maker_reachability=int(_one(values, "decision_maker_reachability")),
            website_manageability=int(_one(values, "website_manageability")),
            no_existing_web_team=int(_one(values, "no_existing_web_team")),
            reason=_one(values, "reason"),
            rejection_reason=rejection,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Qualification values are invalid.") from exc

    if qualification.decision is ProspectDecision.send_to_audit:
        next_status = ProspectStatus.ready_for_audit
    elif qualification.decision is ProspectDecision.hold:
        next_status = ProspectStatus.qualified
    elif rejection is not None:
        next_status = ProspectStatus.unsuitable
    else:
        next_status = ProspectStatus.needs_review

    updated = Prospect.model_validate(
        {
            **prospect.model_dump(mode="json"),
            "qualification": qualification.model_dump(mode="json"),
            "status": next_status,
            "human_verified": True,
            "rejection_reason": rejection.value if rejection is not None else None,
            "updated_at": datetime.now(UTC),
        }
    )
    store = _store(request)
    try:
        store.replace(identity, store.ref(identity, prospect_id), updated)
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)


@router.post("/{prospect_id}/commercial")
async def update_commercial_progress(prospect_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    prospect = _load(request, identity, prospect_id)
    if prospect.status in _TERMINAL_QUALIFICATION_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Terminally rejected or archived prospects cannot enter the commercial funnel.",
        )
    values = _values(await request.body())
    try:
        next_status = ProspectStatus(_one(values, "status"))
        if next_status not in _COMMERCIAL_STATUSES:
            raise ValueError("Unsupported commercial funnel status.")
        if next_status in {
            ProspectStatus.contacted,
            ProspectStatus.responded,
            ProspectStatus.conversation,
        } and not prospect.outreach_eligible:
            raise ValueError("Outreach compliance approval is required before contact progression.")
        first_touch_confirmed = _one(values, "first_touch_compliance_confirmed") == "yes"
        if next_status is ProspectStatus.contacted and prospect.first_touch_compliance_confirmed_at is None:
            if not first_touch_confirmed:
                raise ValueError(
                    "First-touch compliance confirmation is required before initial contact."
                )
            if TenantOutreachSuppressionStore(_root(request)).is_suppressed(
                identity,
                prospect.contact_email,
            ):
                raise ValueError("Suppressed contacts cannot be marked as contacted.")
        loss_raw = _one(values, "commercial_loss_reason")
        loss_reason = (
            ProspectCommercialLossReason(loss_raw)
            if next_status is ProspectStatus.lost and loss_raw
            else None
        )
        updated = Prospect.model_validate(
            {
                **prospect.model_dump(mode="json"),
                "status": next_status,
                "outreach_offer": _one(values, "outreach_offer"),
                "message_variant": _one(values, "message_variant"),
                "commercial_loss_reason": (
                    loss_reason.value if loss_reason is not None else None
                ),
                "commercial_note": _one(values, "commercial_note"),
                "last_contacted_at": _one(values, "last_contacted_at") or None,
                "privacy_notice_provided_at": (
                    datetime.now(UTC)
                    if next_status is ProspectStatus.contacted
                    and prospect.last_contacted_at is None
                    and first_touch_confirmed
                    else prospect.privacy_notice_provided_at
                ),
                "first_touch_compliance_confirmed_at": (
                    datetime.now(UTC)
                    if next_status is ProspectStatus.contacted
                    and prospect.last_contacted_at is None
                    and first_touch_confirmed
                    else prospect.first_touch_compliance_confirmed_at
                ),
                "next_follow_up_at": _one(values, "next_follow_up_at") or None,
                "next_action": _one(values, "next_action"),
                "human_verified": True,
                "updated_at": datetime.now(UTC),
            }
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Commercial funnel values are invalid. Lost prospects require a loss reason.",
        ) from exc

    store = _store(request)
    try:
        store.replace(identity, store.ref(identity, prospect_id), updated)
    except TenantProspectStoreError as exc:
        raise HTTPException(status_code=404, detail="Prospect not found.") from exc
    return RedirectResponse(f"/agency/prospects/{prospect_id}", status_code=303)
