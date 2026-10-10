# ruff: noqa: E501
from __future__ import annotations

import hashlib
import html
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .agency_market_study import (
    all_studies,
    input_json,
    map_points,
    market_detail,
    market_overview,
    store_study,
    study_path,
)
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
from .market_intelligence import (
    DEFAULT_SECTORS,
    CityStudy,
    add_observations,
    import_review,
    manage_queries,
    qualify_business,
    update_shortlist,
)
from .market_intelligence import dashboard as market_dashboard
from .market_intelligence import load as market_load
from .market_intelligence import plan as market_plan
from .prospect_discovery import ObservedBusiness, prospect_from_observation
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
    session_id: str
    manager: AssistedDiscoveryManager | None
    limits: BoundedDiscoveryLimits
    observations: tuple[TraversalObservation, ...] = ()



def _review_store_path(root: Path | None, *, tenant_id: str, session_id: str) -> Path | None:
    if root is None:
        return None
    tenant_key = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()
    return root / "_discovery_reviews" / tenant_key / f"{session_id}.json"


def _save_review(root: Path | None, batch: _DiscoveryReviewBatch) -> None:
    path = _review_store_path(root, tenant_id=batch.tenant_id, session_id=batch.session_id)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tenant_id": batch.tenant_id,
        "session_id": batch.session_id,
        "limits": {
            "max_results": batch.limits.max_results,
            "max_scrolls": batch.limits.max_scrolls,
            "max_elapsed_seconds": batch.limits.max_elapsed_seconds,
            "max_stagnant_scrolls": batch.limits.max_stagnant_scrolls,
        },
        "observations": [
            {
                "business": item.business.model_dump(mode="json"),
                "query_text": item.query_text,
                "query_sequence": item.query_sequence,
                "result_rank": item.result_rank,
                "first_seen_scroll_step": item.first_seen_scroll_step,
            }
            for item in batch.observations
        ],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _load_review(
    root: Path | None,
    *,
    tenant_id: str,
    session_id: str,
) -> _DiscoveryReviewBatch | None:
    path = _review_store_path(root, tenant_id=tenant_id, session_id=session_id)
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("tenant_id") != tenant_id or payload.get("session_id") != session_id:
            return None
        limits = BoundedDiscoveryLimits(**payload["limits"])
        observations = tuple(
            TraversalObservation(
                business=ObservedBusiness.model_validate(item["business"]),
                query_text=str(item["query_text"]),
                query_sequence=int(item["query_sequence"]),
                result_rank=int(item["result_rank"]),
                first_seen_scroll_step=int(item["first_seen_scroll_step"]),
            )
            for item in payload["observations"]
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return _DiscoveryReviewBatch(
        tenant_id=tenant_id,
        session_id=session_id,
        manager=None,
        limits=limits,
        observations=observations,
    )


def _delete_review(root: Path | None, *, tenant_id: str, session_id: str) -> None:
    path = _review_store_path(root, tenant_id=tenant_id, session_id=session_id)
    if path is not None:
        path.unlink(missing_ok=True)


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
                session_id=session.session_id,
                manager=manager,
                limits=limits,
            )
            return session.session_id

    def snapshot(
        self,
        *,
        tenant_id: str,
        session_id: str,
        root: Path | None = None,
    ) -> _DiscoveryReviewBatch:
        with self._lock:
            return self._require(
                tenant_id=tenant_id,
                session_id=session_id,
                root=root,
            )

    def collect(
        self,
        *,
        tenant_id: str,
        session_id: str,
        limits: BoundedDiscoveryLimits | None = None,
        root: Path | None = None,
    ) -> _DiscoveryReviewBatch:
        with self._lock:
            batch = self._require(tenant_id=tenant_id, session_id=session_id, root=root)
            if batch.manager is None:
                raise ValueError("The live discovery browser session is no longer available.")
            if limits is not None:
                batch.limits = limits
            try:
                batch.manager.mark_ready(session_id)
                session = batch.manager.collect(session_id, limits=batch.limits)
                batch.observations = session.observations
                _save_review(root, batch)
                return batch
            finally:
                batch.manager.stop(session_id)

    def finish(
        self,
        *,
        tenant_id: str,
        session_id: str,
        root: Path | None = None,
    ) -> None:
        with self._lock:
            batch = self._require(tenant_id=tenant_id, session_id=session_id, root=root)
            if batch.manager is not None:
                batch.manager.stop(session_id)
            _delete_review(root, tenant_id=tenant_id, session_id=session_id)
            if self._batch is not None and self._batch.session_id == session_id:
                self._batch = None

    def _require(
        self,
        *,
        tenant_id: str,
        session_id: str,
        root: Path | None = None,
    ) -> _DiscoveryReviewBatch:
        batch = self._batch
        if batch is not None and batch.tenant_id == tenant_id and batch.session_id == session_id:
            return batch
        restored = _load_review(root, tenant_id=tenant_id, session_id=session_id)
        if restored is not None:
            self._batch = restored
            return restored
        raise ValueError("Discovery review was not found.")


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
    market_attach_form: str = "",
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
    body = f"""{navigation}<div class='agency-workbench'><section class='workbench-head'><h1>Review digital-presence opportunities</h1>
    <p><strong>{len(batch.observations)}</strong> captured · <strong>{selectable}</strong> selectable · <strong>{no_website}</strong> have no website observed.</p>
    <p class='notice warning'>Rows initially use VERIDRA's deterministic opportunity score, not Google rank. A missing website is a valid Webify opportunity. Sorting changes only what you see; it never changes the stored Google Maps rank or makes outreach automatic.</p>
    <div class='review-tools'>
      <form method='get' action='{review_url}'>
        <label for='sort_results'>Sort results</label>
        <select id='sort_results' name='sort'>{options}</select>
        <input type='hidden' name='select' value='{'all' if select_all else 'none'}'>
        <button type='submit'>Apply sort</button>
      </form>
      <div class='actions'>
        <a class='button secondary' href='{review_url}?sort={html.escape(sort_mode, quote=True)}&select=all'>Select all rows</a>
        <a class='button secondary' href='{review_url}?sort={html.escape(sort_mode, quote=True)}&select=none'>Clear selection</a>
      </div>
    </div>
    <p class='hint'>Select rows individually below, or use Select all rows. Sponsored rows remain excluded. Use Ingest selected opportunities only when the rows you want are checked.</p></section><section class='workbench-body'><div class='workbench-scroll'>
    <form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/ingest'>
      {_review_table(batch.observations, sort_mode=sort_mode, select_all=select_all)}
      <p><button type='submit'>Ingest selected opportunities</button></p>
    </form>
    {market_attach_form}
    <form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/cancel'><button class='secondary' type='submit'>Discard review</button></form>
    </div></section></div>"""
    return HTMLResponse(_page("Review discovered opportunities", body))


@router.get("", response_class=HTMLResponse)
def discovery_page(request: Request) -> str:
    identity = _identity(request)
    navigation = agency_navigation(identity, current="prospect-discovery")
    body = f"""{navigation}<div class='agency-workbench'><section class='workbench-head'><h1>Find prospects</h1>
    <p class='muted'>Choose a business type and location. VERIDRA fills technical location fields and safe search limits automatically. Nothing is saved until you review and select a business.</p></section><section class='workbench-body'><div class='workbench-scroll'>
    <form method='post' action='/agency/prospects/discover/start'>
      <div class='row'>
        <div>
          <label for='business_type'>What business?</label>
          <input id='business_type' name='business_type' maxlength='120' placeholder='dentist, lawyer, physiotherapist…' required>
          <div class='hint'>Use the normal business category you would search in Google Maps.</div>
        </div>
        <div>
          <label for='location'>Where?</label>
          <input id='location' name='location' list='location_suggestions' maxlength='160' placeholder='Dublin, Ireland' autocomplete='off' required>
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
      <details class='advanced' id='advanced-options'>
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
    </form></div></section></div>"""
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



def _market_study(request: Request, study_id: str) -> CityStudy:
    identity = _identity(request)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    path = study_path(root, identity.tenant_id, study_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Market study not found")
    return market_load(path)


@router.get("/market", response_class=HTMLResponse)
def market_index(request: Request) -> str:
    identity = _identity(request)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    return _page("City Market Intelligence", agency_navigation(identity, current="prospect-discovery") + market_overview(root, identity.tenant_id))


@router.post("/market/new", response_model=None)
async def market_new(request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    values = _values(await request.body())
    raw = _one(values, "sectors")
    sectors = tuple(s.strip() for s in raw.split(",") if s.strip()) if raw else DEFAULT_SECTORS
    try:
        study = market_plan(_one(values, "city"), _one(values, "country"), sectors)
        store_study(root, identity.tenant_id, study)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/agency/prospects/discover/market/" + study.study_id, status_code=303)


@router.get("/market/{study_id}", response_class=HTMLResponse)
def market_show(study_id: str, request: Request) -> str:
    identity = _identity(request)
    return _page("City market study", agency_navigation(identity, current="prospect-discovery") + market_detail(_market_study(request, study_id)))


@router.get("/market/{study_id}/selection.js", response_model=None)
def market_selection_script(study_id: str, request: Request) -> Response:
    _market_study(request, study_id)
    script = """
(function () {
  'use strict';
  const root = document.querySelector('.market-workbench');
  if (!root) return;
  if (window.location.hash === '#market-businesses') {
    const details = root.querySelector('.market-bottom');
    if (details) details.open = true;
  }
  const all = root.querySelector('#market-select-all');
  const boxes = Array.from(root.querySelectorAll(
    'input[type=checkbox][form=market-bulk][name=sector]'
  ));
  function synchronize() {
    if (!all) return;
    all.checked = boxes.length > 0 && boxes.every(box => box.checked);
    all.indeterminate = boxes.some(box => box.checked) && !all.checked;
  }
  if (all) all.addEventListener('change', function () {
    boxes.forEach(box => { box.checked = all.checked; });
    synchronize();
  });
  boxes.forEach(box => box.addEventListener('change', synchronize));
  const edit = root.querySelector('#market-edit-button');
  if (edit) edit.addEventListener('click', function () {
    const details = root.querySelector('.market-bottom');
    const tab = root.querySelector('#market-tab-edit');
    if (details && tab) { details.open = true; tab.checked = true; }
  });
  const deletion = root.querySelector('#market-delete-selected');
  if (deletion) deletion.addEventListener('click', function (event) {
    if (!boxes.some(box => box.checked)) { event.preventDefault(); return; }
    if (!confirm('Delete selected searches from plan? Saved businesses will remain.')) {
      event.preventDefault();
    }
  });
  // Candidate triage is presentation-only: it never mutates the study or CRM.
  const search = root.querySelector('#market-business-search');
  const sector = root.querySelector('#market-business-sector');
  const score = root.querySelector('#market-business-score');
  const website = root.querySelector('#market-business-website');
  const review = root.querySelector('#market-business-review');
  const count = root.querySelector('#market-business-count');
  const rows = Array.from(root.querySelectorAll('.market-business-row'));
  function filterBusinesses() {
    if (!search || !sector || !score || !website || !review || !count) return;
    const term = search.value.trim().toLocaleLowerCase();
    let shown = 0;
    rows.forEach(row => {
      const names = row.dataset.name || '';
      const sectors = (row.dataset.sectors || '').split('|');
      const sectorMatch = !sector.value || sectors.includes(sector.value);
      const match = names.includes(term) && sectorMatch
        && Number(row.dataset.score || 0) >= Number(score.value)
        && (!website.value || row.dataset.website === website.value)
        && (!review.value || (review.value === 'unreviewed'
            ? !row.dataset.review : row.dataset.review === review.value));
      row.hidden = !match;
      if (!match) row.querySelector('input[name=business_id]').checked = false;
      if (match) shown++;
    });
    count.textContent = shown + ' of ' + rows.length + ' businesses';
    if (typeof syncBusinessSelect === 'function') syncBusinessSelect();
  }
  [search, sector, score, website, review].forEach(input => {
    if (input) input.addEventListener('input', filterBusinesses);
  });
  const reset = root.querySelector('#market-business-reset');
  if (reset) reset.addEventListener('click', () => {
    if (search) search.value = '';
    if (sector) sector.value = '';
    if (score) score.value = '0';
    if (website) website.value = '';
    if (review) review.value = '';
    filterBusinesses();
  });
  const businessAll = root.querySelector('#market-select-businesses');
  const businessChecks = rows.map(row => row.querySelector('input[name=business_id]'));
  function syncBusinessSelect() {
    if (!businessAll) return;
    const visible = rows.filter(row => !row.hidden).map(row => row.querySelector('input[name=business_id]'));
    businessAll.checked = visible.length > 0 && visible.every(box => box.checked);
    businessAll.indeterminate = visible.some(box => box.checked) && !businessAll.checked;
  }
  if (businessAll) businessAll.addEventListener('change', () => {
    rows.filter(row => !row.hidden).forEach(row => {
      row.querySelector('input[name=business_id]').checked = businessAll.checked;
    });
    syncBusinessSelect();
  });
  businessChecks.forEach(box => box.addEventListener('change', syncBusinessSelect));
  const shortlistForm = root.querySelector('#market-shortlist-form');
  if (shortlistForm) shortlistForm.addEventListener('submit', event => {
    if (!businessChecks.some(box => box.checked)) event.preventDefault();
  });
  filterBusinesses();
  syncBusinessSelect();
  synchronize();
}());
"""
    return Response(
        content=script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/market/{study_id}/qualify", response_model=None)
async def market_qualify(study_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    fields = _values(await request.body())
    try:
        updated = qualify_business(
            _market_study(request, study_id),
            _one(fields, "business_id"),
            _one(fields, "notes"),
        )
        store_study(root, identity.tenant_id, updated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        "/agency/prospects/discover/market/" + study_id + "#market-businesses",
        status_code=303,
    )


@router.post("/market/{study_id}/promote", response_model=None)
async def market_promote(study_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    fields = _values(await request.body())
    business_id = _one(fields, "business_id")
    study = _market_study(request, study_id)
    record = next((r for r in study.businesses if r.business_id == business_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Business not found")
    if not study.qualifications.get(business_id, "").strip():
        raise HTTPException(status_code=409, detail="Save qualification evidence before CRM promotion")
    if business_id not in study.crm_promoted:
        prospect = prospect_from_observation(record.business)
        try:
            TenantProspectDiscoveryIngestor(root).ingest(identity, [prospect])
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        updated = study.model_copy(deep=True)
        updated.crm_promoted.append(business_id)
        store_study(root, identity.tenant_id, updated)
    return RedirectResponse(
        "/agency/prospects/discover/market/" + study_id + "#market-businesses",
        status_code=303,
    )


@router.post("/market/{study_id}/shortlist", response_model=None)
async def market_shortlist(study_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    fields = _values(await request.body())
    try:
        updated = update_shortlist(
            _market_study(request, study_id), fields.get("business_id", []),
            _one(fields, "action"),
        )
        store_study(root, identity.tenant_id, updated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        "/agency/prospects/discover/market/" + study_id + "#market-businesses",
        status_code=303,
    )


@router.post("/market/{study_id}/manage", response_model=None)
async def market_manage(study_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    study = _market_study(request, study_id)
    fields = _values(await request.body())
    action = _one(fields, "action")
    sectors = fields.get("sector", [])
    if action == "queue_all":
        action = "queue"
        sectors = [q.sector for q in study.queries]
    elif action in {"activate_all", "deactivate_all"}:
        action, sectors = action.replace("_all", ""), [q.sector for q in study.queries]
    try:
        updated = manage_queries(
            study, action, sectors, sector=_one(fields, "edit_sector"),
            query_text=_one(fields, "query_text"),
            active=True,
        )
        store_study(root, identity.tenant_id, updated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        "/agency/prospects/discover/market/" + study_id, status_code=303
    )


@router.post("/market/{study_id}/start", response_model=None)
async def market_start(study_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    study = _market_study(request, study_id)
    sector = _one(_values(await request.body()), "sector")
    query = next((q for q in study.queries if q.sector == sector), None)
    if query is None:
        raise HTTPException(status_code=400, detail="Search is not in study")
    try:
        session = _REGISTRY.start(
            tenant_id=identity.tenant_id, query_text=query.query_text,
            country_code=study.country_code, locality=study.city,
            administrative_area="",
            limits=BoundedDiscoveryLimits(max_results=50, max_scrolls=20, max_elapsed_seconds=90),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse("/agency/prospects/discover/" + session, status_code=303)



@router.get("/market/{study_id}/map-view", response_class=HTMLResponse)
def market_map_view(study_id: str, request: Request) -> HTMLResponse:
    study = _market_study(request, study_id)
    # Dedicated same-origin iframe: no inline executable JS.
    # Limit third-party script and tiles to explicitly named providers.
    csp = (
        "default-src 'none'; "
        "script-src 'self' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https://tile.openstreetmap.org; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
    )
    body = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(study.city)} business map</title>"
        "<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'>"
        "<style>html,body,#map{height:100%;width:100%;margin:0;background:#132633}"
        "#legend{position:absolute;right:12px;top:12px;z-index:9999;"
        "background:#102838ee;color:#edf5fc;padding:9px 12px;border-radius:9px;"
        "font:13px/1.7 system-ui,sans-serif;box-shadow:0 2px 12px #0007}"
        "#legend strong{display:block;font-size:14px}"
        "#legend .dot{display:inline-block;width:11px;height:11px;border-radius:50%;"
        "margin-right:8px;border:1px solid #081e2a}"
        "#error{position:absolute;top:12px;left:48px;z-index:9999;"
        "background:#fff;padding:8px;display:none;color:#222}</style>"
        "</head><body><div id='map'></div>"
        "<aside id='legend' aria-label='Discovery score legend'>"
        "<strong>Discovery score</strong>"
        "<div><span class='dot' style='background:#e27354'></span>65–100 · High</div>"
        "<div><span class='dot' style='background:#3ea9b8'></span>0–64 · Other</div>"
        "</aside><p id='error' role='alert'>"
        "Map could not load; see the candidate table below the map.</p>"
        "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script>"
        f"<script src='/agency/prospects/discover/market/{study_id}/map-script'></script>"
        "</body></html>"
    )
    return HTMLResponse(body, headers={"Content-Security-Policy": csp, "Cache-Control": "no-store"})


@router.get("/market/{study_id}/map-script", response_model=None)
def market_map_script(study_id: str, request: Request) -> Response:
    study = _market_study(request, study_id)
    payload = json.dumps(map_points(study), ensure_ascii=False).replace("<", "\\u003c")
    source = """
(function () {
  'use strict';
  if (typeof L === 'undefined') {
    document.getElementById('error').style.display = 'block';
    return;
  }
  const points = __POINTS__;
  if (!points.length) return;
  const map = L.map('map', { scrollWheelZoom: true });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors', maxZoom: 18
  }).addTo(map);
  const bounds = [];
  points.forEach(function (p) {
    const color = p.score >= 65 ? '#e27354' : '#3ea9b8';
    const marker = L.circleMarker([p.lat, p.lon], {
      radius: 8, color: '#122330', weight: 2, fillColor: color, fillOpacity: 0.95
    }).addTo(map);
    const el = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = p.name + ' — ' + p.score + '/100';
    const line = document.createElement('div');
    const link = document.createElement('a');
    link.href = p.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Open Google Maps listing';
    line.appendChild(link);
    el.appendChild(title);
    el.appendChild(line);
    marker.bindPopup(el);
    bounds.push([p.lat, p.lon]);
  });
  map.fitBounds(bounds, { padding: [25, 25], maxZoom: 13 });
}());
"""
    return Response(
        content=source.replace("__POINTS__", payload),
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/market/{study_id}/export", response_model=None)
def market_export(study_id: str, request: Request) -> Response:
    return Response(content=input_json(_market_study(request, study_id)),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="VERIDRA_MARKET_ANALYSIS_INPUT.json"'})


@router.get("/market/{study_id}/report", response_class=HTMLResponse)
def market_report(study_id: str, request: Request) -> str:
    return market_dashboard(_market_study(request, study_id))


@router.post("/market/{study_id}/import-review", response_model=None)
async def market_import_ai(study_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    study = _market_study(request, study_id)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    try:
        payload = json.loads(_one(_values(await request.body()), "review_json"))
        updated = import_review(study, payload)
        store_study(root, identity.tenant_id, updated)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/agency/prospects/discover/market/" + study_id, status_code=303)


@router.post("/{session_id}/attach-market", response_model=None)
async def market_attach(session_id: str, request: Request) -> RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    study_id = _one(values, "study_id")
    sector = _one(values, "sector")
    study = _market_study(request, study_id)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    try:
        batch = _REGISTRY.snapshot(tenant_id=identity.tenant_id, session_id=session_id, root=root)
        query = next(q for q in study.queries if q.sector == sector)
        if any(item.query_text != query.query_text for item in batch.observations):
            raise ValueError("Captured query does not match this study")
        if not batch.observations:
            raise ValueError("No observations available")
        updated = add_observations(study, sector, [item.business for item in batch.observations if not _is_sponsored(item)])
        updated.batch_queue = [name for name in updated.batch_queue if name != sector]
        store_study(root, identity.tenant_id, updated)
        _REGISTRY.finish(tenant_id=identity.tenant_id, session_id=session_id, root=root)
    except (ValueError, StopIteration) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/agency/prospects/discover/market/" + study_id, status_code=303)



@router.post("/{session_id}/collect-market", response_model=None)
async def collect_into_market(session_id: str, request: Request) -> HTMLResponse | RedirectResponse:
    """Collect once and safely complete a city-study capture.

    On capture/storage errors, preserve any saved review for recovery. Never
    strand the operator on an unhandled 500 with a locked discovery session.
    """
    identity = _identity(request)
    _trusted_origin(request)
    root = _root(request)
    if root is None:
        raise HTTPException(status_code=503, detail="Market storage unavailable")
    try:
        batch = _REGISTRY.snapshot(
            tenant_id=identity.tenant_id, session_id=session_id, root=root
        )
        if batch.observations:
            query_text = batch.observations[0].query_text
        elif batch.manager is not None:
            query_text = batch.manager.snapshot().query_text
        else:
            raise ValueError("No captured results remain for this session.")

        matches = [
            (study, query.sector)
            for study in all_studies(root, identity.tenant_id)
            for query in study.queries
            if query.query_text == query_text
        ]
        if len(matches) != 1:
            raise ValueError("Expected exactly one matching market query")
        study, sector = matches[0]

        # A previous capture may already be persisted. Reuse it instead of
        # collecting a second time from an already stopped browser.
        if not batch.observations:
            if batch.manager is None:
                raise ValueError("The discovery browser is no longer active.")
            batch = _REGISTRY.collect(
                tenant_id=identity.tenant_id, session_id=session_id,
                limits=batch.limits, root=root,
            )

        if any(item.query_text != query_text for item in batch.observations):
            raise ValueError("Captured query mismatch")
        if not batch.observations:
            raise ValueError("The search returned no results; study was not changed.")

        updated = add_observations(
            study, sector,
            [item.business for item in batch.observations if not _is_sponsored(item)],
        )
        store_study(root, identity.tenant_id, updated)
        _REGISTRY.finish(
            tenant_id=identity.tenant_id, session_id=session_id, root=root
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Market study collection failed for session %s", session_id)
        safe_session = html.escape(session_id, quote=True)
        message = html.escape(str(exc)) if isinstance(exc, (RuntimeError, ValueError, OSError)) else "An unexpected collection error occurred; see server logs."
        body = (
            "<section><h1>Market collection could not finish</h1>"
            f"<p class='notice warning'>{message}</p>"
            "<p>The previous study has not been overwritten. If the results "
            "were already captured, they may be available in the saved review.</p>"
            f"<p><a class='button' href='/agency/prospects/discover/{safe_session}/review'>"
            "Review saved results</a></p>"
            f"<form method='post' action='/agency/prospects/discover/{safe_session}/cancel'>"
            "<button type='submit'>Discard this session and unlock Discovery</button>"
            "</form><p><a href='/agency/prospects/discover/market'>"
            "Return to Market Studies</a></p></section>"
        )
        return HTMLResponse(
            _page("Market collection recovery", body), status_code=409
        )
    return RedirectResponse(
        "/agency/prospects/discover/market/" + study.study_id, status_code=303
    )


@router.get("/{session_id}", response_class=HTMLResponse)
def discovery_waiting(session_id: str, request: Request) -> str:
    identity = _identity(request)
    try:
        batch = _REGISTRY.snapshot(
            tenant_id=identity.tenant_id,
            session_id=session_id,
            root=_root(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if batch.manager is None:
        raise HTTPException(
            status_code=409,
            detail="The browser session ended; reopen the saved review instead.",
        )
    session = batch.manager.snapshot()
    navigation = agency_navigation(identity, current="prospect-discovery")
    market_root = _root(request)
    matches = sum(
        query.query_text == session.query_text
        for study in all_studies(market_root, identity.tenant_id)
        for query in study.queries
    ) if market_root is not None else 0
    guided_action = (
        "<form method='post' action='/agency/prospects/discover/"
        + html.escape(session_id, quote=True)
        + "/collect-market'><button type='submit'>Collect and add to Market Study</button></form>"
        if matches == 1 else ""
    )
    body = f"""{navigation}<div class='agency-workbench'><section class='workbench-head'><h1>Browser opened</h1>
    <p class='notice'>In the visible Chromium window, complete any normal Google sign-in/consent step and make sure the actual Maps result list for <strong>{html.escape(session.query_text)}</strong> is visible. Then return here and collect the bounded sample.</p></section><section class='workbench-body'><div class='workbench-scroll'>
    <form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/collect'>
      <div class='compact-fields'>
        <div><label for='max_results'>Results to capture</label><input id='max_results' name='max_results' type='number' min='1' max='200' value='{batch.limits.max_results}'></div>
        <div><label for='max_scrolls'>Maximum scrolls</label><input id='max_scrolls' name='max_scrolls' type='number' min='0' max='100' value='{batch.limits.max_scrolls}'></div>
        <div><label for='max_seconds'>Maximum seconds</label><input id='max_seconds' name='max_seconds' type='number' min='1' max='300' step='1' value='{batch.limits.max_elapsed_seconds:g}'></div>
      </div>
      <p class='hint'>You can change these capture limits now without restarting the discovery. VERIDRA still enforces the bounded safety maximums.</p>
      <div class='actions'><button type='submit'>Collect visible results</button></div>
    </form>
    {guided_action}\n    <form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/cancel'><button class='secondary' type='submit'>Cancel</button></form>
    </div></section></div>"""
    return _page("Discovery browser ready", body)


@router.post(
    "/{session_id}/collect",
    response_class=HTMLResponse,
    response_model=None,
)
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
            root=_root(request),
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
            root=_root(request),
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
            root=_root(request),
        )
    except ValueError:
        navigation = agency_navigation(identity, current="prospect-discovery")
        return HTMLResponse(
            _page(
                "Discovery review unavailable",
                f"{navigation}<section><h1>Discovery review unavailable</h1>"
                "<p class='muted'>This review is no longer available. Start a new prospect discovery; completed reviews created after this update persist across VERIDRA restarts until they are ingested or discarded.</p>"
                "<p><a class='button' href='/agency/prospects/discover'>Start new discovery</a></p></section>",
            ),
            status_code=404,
        )
    market_attach_form = ""
    root = _root(request)
    if root is not None and batch.observations:
        for study in all_studies(root, identity.tenant_id):
            for query in study.queries:
                if batch.observations[0].query_text == query.query_text:
                    market_attach_form += (
                        "<form method='post' action='/agency/prospects/discover/"
                        + html.escape(session_id, quote=True)
                        + "/attach-market'><input type='hidden' name='study_id' value='"
                        + study.study_id + "'><input type='hidden' name='sector' value='"
                        + html.escape(query.sector, quote=True)
                        + "'><button type='submit'>Add results to "
                        + html.escape(study.city) + " study</button></form>"
                    )
    return _review_response(
        market_attach_form=market_attach_form,
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
        batch = _REGISTRY.snapshot(
            tenant_id=identity.tenant_id,
            session_id=session_id,
            root=_root(request),
        )
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
            _REGISTRY.finish(
                tenant_id=identity.tenant_id,
                session_id=session_id,
                root=_root(request),
            )

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
        _REGISTRY.finish(
            tenant_id=identity.tenant_id,
            session_id=session_id,
            root=_root(request),
        )
    except ValueError:
        pass
    return RedirectResponse("/agency/prospects/discover", status_code=303)