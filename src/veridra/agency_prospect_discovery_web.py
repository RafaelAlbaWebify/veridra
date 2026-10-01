# ruff: noqa: E501
from __future__ import annotations

import html
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .agency_navigation import agency_navigation
from .assisted_browser_provider import SubprocessPlaywrightDiscoveryProvider
from .assisted_discovery import (
    AssistedDiscoveryManager,
    BoundedDiscoveryLimits,
    TraversalObservation,
)
from .assisted_discovery_acceptance_cli import build_start_url
from .identity_tenancy import (
    IdentityBoundaryError,
    RequestIdentity,
    TenantCapability,
    require_tenant_capability,
)
from .prospect_discovery import prospect_from_observation
from .prospect_ingest import DiscoveryIngestAction, TenantProspectDiscoveryIngestor
from .prospect_opportunity import assess_opportunity
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy

router = APIRouter(prefix="/agency/prospects/discover", tags=["agency-prospect-discovery"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1250px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.warning{border-left-color:#b7791f;background:#fff8e6}.actions{display:flex;gap:8px;flex-wrap:wrap}label{display:block;font-weight:700;margin:12px 0 5px}input{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}.row{display:grid;grid-template-columns:2fr 1fr;gap:14px}.row.three{grid-template-columns:1fr 1fr 1fr}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}th{font-size:12px;color:#5d6670}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}.check{width:auto}.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}.priority{font-weight:700}.reason{max-width:330px}.reason span{display:block;margin-bottom:4px}.advanced{margin-top:18px;border-top:1px solid #e5e7eb;padding-top:14px}.advanced summary{cursor:pointer;font-weight:700}.hint{font-size:12px;color:#68707a;margin-top:5px}.review-tools{display:flex;gap:12px;align-items:end;justify-content:space-between;flex-wrap:wrap;margin:16px 0}.review-tools label{margin:0 0 5px}.review-tools select{min-width:250px;padding:9px;border:1px solid #cfd4da;border-radius:7px;background:#fff}.compact-fields{display:grid;grid-template-columns:repeat(3,minmax(130px,1fr));gap:12px;max-width:620px;margin:14px 0}.compact-fields label{margin-top:0}@media(max-width:760px){.compact-fields{grid-template-columns:1fr}}@media(max-width:760px){.row,.row.three{grid-template-columns:1fr}table{display:block;overflow:auto}}
"""


@dataclass(slots=True)
class _DiscoveryReviewBatch:
    tenant_id: str
    manager: AssistedDiscoveryManager
    limits: BoundedDiscoveryLimits
    observations: tuple[TraversalObservation, ...] = ()


class _DiscoveryRegistry:
    """Hold one local operator-controlled browser session at a time."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._batch: _DiscoveryReviewBatch | None = None

    def start(
        self,
        *,
        tenant_id: str,
        query_text: str,
        country_code: str,
        locality: str,
        administrative_area: str,
        limits: BoundedDiscoveryLimits,
    ) -> str:
        with self._lock:
            if self._batch is not None:
                raise ValueError("Another local discovery review is already active.")
            provider = SubprocessPlaywrightDiscoveryProvider(
                country_code=country_code,
                locality=locality,
                administrative_area=administrative_area,
            )
            manager = AssistedDiscoveryManager(provider)
            session = manager.launch(
                query_text=query_text,
                query_sequence=1,
                start_url=build_start_url(query_text),
            )
            if session.session_id is None:
                manager.stop()
                raise ValueError("Discovery session did not receive an identifier.")
            self._batch = _DiscoveryReviewBatch(
                tenant_id=tenant_id,
                manager=manager,
                limits=limits,
            )
            return session.session_id

    def snapshot(self, *, tenant_id: str, session_id: str) -> _DiscoveryReviewBatch:
        with self._lock:
            return self._require(tenant_id=tenant_id, session_id=session_id)

    def collect(
        self,
        *,
        tenant_id: str,
        session_id: str,
        limits: BoundedDiscoveryLimits | None = None,
    ) -> _DiscoveryReviewBatch:
        with self._lock:
            batch = self._require(tenant_id=tenant_id, session_id=session_id)
            if limits is not None:
                batch.limits = limits
            try:
                batch.manager.mark_ready(session_id)
                session = batch.manager.collect(session_id, limits=batch.limits)
                batch.observations = session.observations
                return batch
            finally:
                batch.manager.stop(session_id)

    def finish(self, *, tenant_id: str, session_id: str) -> None:
        with self._lock:
            batch = self._require(tenant_id=tenant_id, session_id=session_id)
            batch.manager.stop(session_id)
            self._batch = None

    def _require(self, *, tenant_id: str, session_id: str) -> _DiscoveryReviewBatch:
        batch = self._batch
        if batch is None or batch.tenant_id != tenant_id:
            raise ValueError("Discovery review was not found.")
        snapshot = batch.manager.snapshot()
        if snapshot.session_id != session_id:
            raise ValueError("Discovery review was not found.")
        return batch


_REGISTRY = _DiscoveryRegistry()


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{body}</main></body></html>"


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _identity(request: Request) -> RequestIdentity:
    identity = require_request_identity(request)
    try:
        require_tenant_capability(identity, TenantCapability.manage_leads)
    except IdentityBoundaryError as exc:
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    return identity


def _trusted_origin(request: Request) -> None:
    configured = os.environ.get("VERIDRA_TRUSTED_ORIGIN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Prospect discovery is not configured.")
    try:
        TrustedSameOriginPolicy(configured).validate(request)
    except SameOriginRequestError as exc:
        raise HTTPException(status_code=403, detail="Prospect discovery request is not permitted.") from exc


def _values(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8"), keep_blank_values=True)


def _one(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def _int(values: dict[str, list[str]], name: str, default: int) -> int:
    raw = _one(values, name)
    return int(raw) if raw else default


def _float(values: dict[str, list[str]], name: str, default: float) -> float:
    raw = _one(values, name)
    return float(raw) if raw else default


_COUNTRY_NAME_TO_CODE = {
    "ireland": "IE",
    "spain": "ES",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "united states": "US",
    "usa": "US",
    "canada": "CA",
    "australia": "AU",
    "new zealand": "NZ",
}


def _location_defaults(location: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in location.split(",") if part.strip()]
    locality = parts[0] if parts else ""
    country_code = _COUNTRY_NAME_TO_CODE.get(parts[-1].casefold(), "") if parts else ""
    return locality, locality, country_code


def _infer_sector_from_name(name: str) -> str:
    folded = name.casefold()
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
    for token, sector in rules:
        if token in folded:
            return sector
    return ""


def _clean_sector(observation: TraversalObservation) -> str:
    category = observation.business.category.strip()
    if category.casefold() == observation.business.name.casefold():
        return ""
    if category.casefold() == "sponsored":
        return ""
    if category:
        return category
    return _infer_sector_from_name(observation.business.name)


def _is_sponsored(observation: TraversalObservation) -> bool:
    return observation.business.category.strip().casefold() in {
        "sponsored",
        "ad",
        "advertisement",
    }


def _prospect_for_ingest(observation: TraversalObservation):  # type: ignore[no-untyped-def]
    business = observation.business.model_copy(update={"category": _clean_sector(observation)})
    prospect = prospect_from_observation(business)
    opportunity = assess_opportunity(business)
    rating = f"{business.rating:g}" if business.rating is not None else "unknown"
    reviews = str(business.review_count) if business.review_count is not None else "unknown"
    photos = (
        str(business.profile_photo_signal_count)
        if business.profile_photo_signal_count is not None
        else "unknown"
    )
    reasons = " ".join(opportunity.reasons)
    evidence = (
        f"{prospect.evidence_summary}\nGoogle Maps discovery query: {observation.query_text}. "
        f"Result rank: {observation.result_rank}. Rating: {rating}. Reviews: {reviews}. "
        f"Photo signal: {photos}. Digital-presence opportunity: {opportunity.band.value} "
        f"({opportunity.score}/100; gap {opportunity.digital_gap_score}, activity "
        f"{opportunity.business_activity_score}). {reasons}"
    )
    discovery = {
        "query_text": observation.query_text,
        "result_rank": observation.result_rank,
        "opportunity_score": opportunity.score,
        "opportunity_band": opportunity.band.value,
        "digital_gap_score": opportunity.digital_gap_score,
        "business_activity_score": opportunity.business_activity_score,
        "rating": business.rating,
        "review_count": business.review_count,
        "photo_signal_count": business.profile_photo_signal_count,
        "observed_at": business.observed_at,
    }
    return type(prospect).model_validate(
        {
            **prospect.model_dump(mode="json"),
            "evidence_summary": evidence[-4000:],
            "discovery": discovery,
        }
    )


def _sorted_observations(
    observations: tuple[TraversalObservation, ...],
    sort_mode: str,
) -> tuple[TraversalObservation, ...]:
    if sort_mode == "rank-asc":
        return tuple(sorted(observations, key=lambda item: item.result_rank))
    if sort_mode == "rating-desc":
        return tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.business.rating if item.business.rating is not None else -1,
                    item.business.review_count or 0,
                    -item.result_rank,
                ),
                reverse=True,
            )
        )
    if sort_mode == "reviews-desc":
        return tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.business.review_count
                    if item.business.review_count is not None
                    else -1,
                    item.business.rating if item.business.rating is not None else -1,
                    -item.result_rank,
                ),
                reverse=True,
            )
        )
    if sort_mode == "name-asc":
        return tuple(
            sorted(
                observations,
                key=lambda item: (item.business.name.casefold(), item.result_rank),
            )
        )
    if sort_mode == "website-asc":
        return tuple(
            sorted(
                observations,
                key=lambda item: (
                    1 if item.business.website is not None else 0,
                    -assess_opportunity(item.business).score,
                    item.result_rank,
                ),
            )
        )
    return tuple(
        sorted(
            observations,
            key=lambda item: (
                assess_opportunity(item.business).score,
                item.business.review_count or 0,
                -item.result_rank,
            ),
            reverse=True,
        )
    )


def _review_table(
    observations: tuple[TraversalObservation, ...],
    *,
    sort_mode: str = "score-desc",
    select_all: bool = False,
) -> str:
    rows: list[str] = []
    for item in _sorted_observations(observations, sort_mode):
        business = item.business
        opportunity = assess_opportunity(business)
        website = str(business.website) if business.website is not None else "No website observed"
        source = str(business.source_url) if business.source_url is not None else ""
        checkbox = (
            "<span class='muted'>Sponsored</span>"
            if _is_sponsored(item)
            else (
                f"<input class='check' type='checkbox' name='selected_rank' "
                f"value='{item.result_rank}'{' checked' if select_all else ''}>"
            )
        )
        sector = _clean_sector(item) or "Unclassified"
        source_link = (
            f"<a href='{html.escape(source, quote=True)}' target='_blank' rel='noopener'>Maps</a>"
            if source
            else "—"
        )
        rating = f"{business.rating:g}" if business.rating is not None else "—"
        reviews = str(business.review_count) if business.review_count is not None else "—"
        photos = (
            str(business.profile_photo_signal_count)
            if business.profile_photo_signal_count is not None
            else "—"
        )
        reason_html = "".join(
            f"<span>{html.escape(reason)}</span>" for reason in opportunity.reasons[:3]
        )
        if not reason_html:
            reason_html = "<span class='muted'>No observed digital gap from discovery signals.</span>"
        rows.append(
            "<tr>"
            f"<td>{checkbox}</td>"
            f"<td>{item.result_rank}</td>"
            f"<td><strong>{html.escape(business.name)}</strong><br><span class='muted'>{html.escape(sector)}</span></td>"
            f"<td><span class='badge'>{html.escape(opportunity.band.value.upper())} {opportunity.score}/100</span><br><span class='muted'>gap {opportunity.digital_gap_score} · activity {opportunity.business_activity_score}</span></td>"
            f"<td>{html.escape(website)}</td>"
            f"<td>{rating}</td><td>{reviews}</td><td>{photos}</td>"
            f"<td class='reason'>{reason_html}</td>"
            f"<td>{source_link}</td>"
            "</tr>"
        )
    return (
        "<table id='discovery-results'><thead><tr>"
        "<th>Keep</th><th>Maps rank</th><th>Business</th><th>Opportunity</th>"
        "<th>Website</th><th>Rating</th><th>Reviews</th><th>Photo signal</th>"
        "<th>Why</th><th>Source</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _review_response(
    *,
    identity: RequestIdentity,
    session_id: str,
    batch: _DiscoveryReviewBatch,
    sort_mode: str = "score-desc",
    select_all: bool = False,
) -> HTMLResponse:
    navigation = agency_navigation(identity, current="prospect-discovery")
    selectable = sum(1 for item in batch.observations if not _is_sponsored(item))
    no_website = sum(
        1
        for item in batch.observations
        if item.business.website is None and not _is_sponsored(item)
    )
    sort_options = {
        "score-desc": "Opportunity — highest first",
        "rank-asc": "Google Maps rank — best first",
        "rating-desc": "Rating — highest first",
        "reviews-desc": "Reviews — most first",
        "name-asc": "Business name — A to Z",
        "website-asc": "No website first",
    }
    if sort_mode not in sort_options:
        sort_mode = "score-desc"
    options = "".join(
        f"<option value='{value}'{' selected' if value == sort_mode else ''}>{html.escape(label)}</option>"
        for value, label in sort_options.items()
    )
    review_url = f"/agency/prospects/discover/{html.escape(session_id, quote=True)}/review"
    body = f"""{navigation}<section><h1>Review digital-presence opportunities</h1>
    <p><strong>{len(batch.observations)}</strong> captured · <strong>{selectable}</strong> selectable · <strong>{no_website}</strong> have no website observed.</p>
    <p class='notice warning'>Rows initially use VERIDRA's deterministic opportunity score, not Google rank. A missing website is a valid Webify opportunity. Sorting changes only what you see; it never changes the stored Google Maps rank or makes outreach automatic.</p>
    <div class='review-tools'>
      <form method='get' action='{review_url}'>
        <label for='sort_results'>Sort results</label>
        <select id='sort_results' name='sort'>{options}</select>
        <input type='hidden' name='select' value='{'all' if select_all else 'none'}'>
        <button type='submit'>Apply sort</button>
      </form>
      <form method='get' action='{review_url}'>
        <input type='hidden' name='sort' value='{html.escape(sort_mode, quote=True)}'>
        <label for='select_all' style='margin:0'>
          <input class='check' id='select_all' name='select' type='checkbox' value='all'{' checked' if select_all else ''}>
          Select all
        </label>
        <button class='secondary' type='submit'>Apply selection</button>
      </form>
    </div>
    <p class='hint'>Select all marks every selectable business. Sponsored rows remain excluded. Uncheck it and apply again to clear the selection.</p>
    <form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/ingest'>
      {_review_table(batch.observations, sort_mode=sort_mode, select_all=select_all)}
      <p><button type='submit'>Ingest selected opportunities</button></p>
    </form>
    <form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/cancel'><button class='secondary' type='submit'>Discard review</button></form>
    </section>"""
    return HTMLResponse(_page("Review discovered opportunities", body))


@router.get("", response_class=HTMLResponse)
def discovery_page(request: Request) -> str:
    identity = _identity(request)
    navigation = agency_navigation(identity, current="prospect-discovery")
    body = f"""{navigation}<section><p><a href='/agency/prospects'>← Prospects</a></p><h1>Find prospects</h1>
    <p class='muted'>Tell VERIDRA what kind of business you want and where. Technical location fields and safe search limits are filled automatically. Nothing is saved until you review and select a business.</p>
    <form method='post' action='/agency/prospects/discover/start'>
      <div class='row'>
        <div>
          <label for='business_type'>What business?</label>
          <input id='business_type' name='business_type' maxlength='120' value='dentist' placeholder='dentist, lawyer, physiotherapist…' required>
          <div class='hint'>Use the normal business category you would search in Google Maps.</div>
        </div>
        <div>
          <label for='location'>Where?</label>
          <input id='location' name='location' list='location_suggestions' maxlength='160' value='Dublin, Ireland' placeholder='Dublin, Ireland' autocomplete='off' required>
          <datalist id='location_suggestions'>
            <option value='Dublin, Ireland'></option>
            <option value='Cork, Ireland'></option>
            <option value='Galway, Ireland'></option>
            <option value='Limerick, Ireland'></option>
            <option value='Waterford, Ireland'></option>
            <option value='Kilkenny, Ireland'></option>
          </datalist>
          <div class='hint'>Start typing a city. VERIDRA derives locality, administrative area and country code; Ireland-first suggestions are provided.</div>
        </div>
      </div>
      <details class='advanced'>
        <summary>Advanced options</summary>
        <div class='row'>
          <div><label for='country_code'>Country code</label><input id='country_code' name='country_code' maxlength='2' placeholder='Auto'></div>
          <div><label for='locality'>Locality</label><input id='locality' name='locality' maxlength='120' placeholder='Auto'></div>
        </div>
        <div class='row'>
          <div><label for='administrative_area'>Administrative area</label><input id='administrative_area' name='administrative_area' maxlength='120' placeholder='Auto'></div>
          <div></div>
        </div>
        <div class='row three'>
          <div><label for='max_results'>Maximum results</label><input id='max_results' name='max_results' type='number' min='1' max='200' value='20'></div>
          <div><label for='max_scrolls'>Maximum scrolls</label><input id='max_scrolls' name='max_scrolls' type='number' min='0' max='100' value='10'></div>
          <div><label for='max_seconds'>Maximum seconds</label><input id='max_seconds' name='max_seconds' type='number' min='1' max='300' value='45'></div>
        </div>
      </details>
      <p><button type='submit'>Find prospects</button></p>
    </form></section>"""
    return _page("Find prospects", body)


@router.post("/start", response_model=None)
async def discovery_start(request: Request) -> HTMLResponse | RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    business_type = _one(values, "business_type")
    location = _one(values, "location")
    auto_locality, auto_area, auto_country = _location_defaults(location)
    query = f"{business_type} in {location}" if business_type and location else _one(values, "query")
    country_code = (_one(values, "country_code") or auto_country).upper()
    locality = _one(values, "locality") or auto_locality
    administrative_area = _one(values, "administrative_area") or auto_area
    try:
        limits = BoundedDiscoveryLimits(
            max_results=_int(values, "max_results", 20),
            max_scrolls=_int(values, "max_scrolls", 10),
            max_elapsed_seconds=_float(values, "max_seconds", 45.0),
            max_stagnant_scrolls=3,
        )
        session_id = _REGISTRY.start(
            tenant_id=identity.tenant_id,
            query_text=query,
            country_code=country_code,
            locality=locality,
            administrative_area=administrative_area,
            limits=limits,
        )
    except (TypeError, ValueError) as exc:
        return HTMLResponse(
            _page("Discovery could not start", f"<section><h1>Discovery could not start</h1><p class='muted'>{html.escape(str(exc))}</p><p><a href='/agency/prospects/discover'>Return to discovery</a></p></section>"),
            status_code=400,
        )
    return RedirectResponse(f"/agency/prospects/discover/{session_id}", status_code=303)


@router.get("/{session_id}", response_class=HTMLResponse)
def discovery_waiting(session_id: str, request: Request) -> str:
    identity = _identity(request)
    try:
        batch = _REGISTRY.snapshot(tenant_id=identity.tenant_id, session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session = batch.manager.snapshot()
    navigation = agency_navigation(identity, current="prospect-discovery")
    body = f"""{navigation}<section><h1>Browser opened</h1>
    <p class='notice'>In the visible Chromium window, complete any normal Google sign-in/consent step and make sure the actual Maps result list for <strong>{html.escape(session.query_text)}</strong> is visible. Then return here and collect the bounded sample.</p>
    <form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/collect'>
      <div class='compact-fields'>
        <div><label for='max_results'>Results to capture</label><input id='max_results' name='max_results' type='number' min='1' max='200' value='{batch.limits.max_results}'></div>
        <div><label for='max_scrolls'>Maximum scrolls</label><input id='max_scrolls' name='max_scrolls' type='number' min='0' max='100' value='{batch.limits.max_scrolls}'></div>
        <div><label for='max_seconds'>Maximum seconds</label><input id='max_seconds' name='max_seconds' type='number' min='1' max='300' step='1' value='{batch.limits.max_elapsed_seconds:g}'></div>
      </div>
      <p class='hint'>You can change these capture limits now without restarting the discovery. VERIDRA still enforces the bounded safety maximums.</p>
      <div class='actions'><button type='submit'>Collect visible results</button></div>
    </form>
    <form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/cancel'><button class='secondary' type='submit'>Cancel</button></form>
    </section>"""
    return _page("Discovery browser ready", body)


@router.post("/{session_id}/collect", response_class=HTMLResponse)
async def discovery_collect(
    session_id: str,
    request: Request,
) -> HTMLResponse | RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    try:
        current = _REGISTRY.snapshot(
            tenant_id=identity.tenant_id,
            session_id=session_id,
        )
        limits = BoundedDiscoveryLimits(
            max_results=_int(values, "max_results", current.limits.max_results),
            max_scrolls=_int(values, "max_scrolls", current.limits.max_scrolls),
            max_elapsed_seconds=_float(
                values,
                "max_seconds",
                current.limits.max_elapsed_seconds,
            ),
            max_stagnant_scrolls=current.limits.max_stagnant_scrolls,
        )
        _REGISTRY.collect(
            tenant_id=identity.tenant_id,
            session_id=session_id,
            limits=limits,
        )
    except (RuntimeError, ValueError) as exc:
        return HTMLResponse(
            _page("Discovery collection failed", f"<section><h1>Collection failed</h1><p class='muted'>{html.escape(str(exc))}</p><p><a href='/agency/prospects/discover'>Start another discovery</a></p></section>"),
            status_code=400,
        )
    return RedirectResponse(
        f"/agency/prospects/discover/{session_id}/review",
        status_code=303,
    )


@router.get("/{session_id}/review", response_class=HTMLResponse)
def discovery_review(
    session_id: str,
    request: Request,
    sort: str = "score-desc",
    select: str = "none",
) -> HTMLResponse:
    identity = _identity(request)
    try:
        batch = _REGISTRY.snapshot(
            tenant_id=identity.tenant_id,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _review_response(
        identity=identity,
        session_id=session_id,
        batch=batch,
        sort_mode=sort,
        select_all=select == "all",
    )


@router.post("/{session_id}/ingest", response_class=HTMLResponse)
async def discovery_ingest(session_id: str, request: Request) -> HTMLResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    try:
        batch = _REGISTRY.snapshot(tenant_id=identity.tenant_id, session_id=session_id)
        selected = {int(value) for value in values.get("selected_rank", [])}
        observations = tuple(
            item
            for item in batch.observations
            if item.result_rank in selected and not _is_sponsored(item)
        )
        if not observations:
            raise ValueError("Select at least one discovered business opportunity.")
        prospects = [_prospect_for_ingest(item) for item in observations]
        outcomes = TenantProspectDiscoveryIngestor(_root(request)).ingest(identity, prospects)
    except (TypeError, ValueError) as exc:
        return HTMLResponse(
            _page("Discovery ingest failed", f"<section><h1>Nothing was ingested</h1><p class='muted'>{html.escape(str(exc))}</p><p><a href='/agency/prospects/discover/{html.escape(session_id, quote=True)}'>Return to review</a></p></section>"),
            status_code=400,
        )
    finally:
        if "outcomes" in locals():
            _REGISTRY.finish(tenant_id=identity.tenant_id, session_id=session_id)

    counts = {action: 0 for action in DiscoveryIngestAction}
    for outcome in outcomes:
        counts[outcome.action] += 1
    body = (
        "<section><h1>Selected prospects ingested</h1>"
        f"<p><strong>{len(outcomes)}</strong> selected records processed: "
        f"{counts[DiscoveryIngestAction.created]} created, "
        f"{counts[DiscoveryIngestAction.enriched]} safely enriched, "
        f"{counts[DiscoveryIngestAction.unchanged]} unchanged.</p>"
        "<p class='notice'>Only the businesses you selected were processed. Existing human qualification, rejection, contact, audit and outreach state remains protected by the discovery ingest policy. No-website prospects remain valid leads but cannot enter website-audit stages until a website exists or a website-creation opportunity is handled separately.</p>"
        "<p><a class='button' href='/agency/prospects'>Open prospect workbench</a></p></section>"
    )
    return HTMLResponse(_page("Discovery ingest complete", body))


@router.post("/{session_id}/cancel", response_model=None)
def discovery_cancel(session_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    try:
        _REGISTRY.finish(tenant_id=identity.tenant_id, session_id=session_id)
    except ValueError:
        pass
    return RedirectResponse("/agency/prospects/discover", status_code=303)