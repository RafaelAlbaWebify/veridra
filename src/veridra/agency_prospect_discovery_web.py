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
from .request_security import require_request_identity
from .same_origin import SameOriginRequestError, TrustedSameOriginPolicy

router = APIRouter(prefix="/agency/prospects/discover", tags=["agency-prospect-discovery"])

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#17191c;font:14px Arial,sans-serif}main{max-width:1100px;margin:36px auto;padding:0 20px}section{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:24px;margin-bottom:18px}.button,button{display:inline-block;border:0;border-radius:7px;background:#22272d;color:#fff;padding:10px 14px;text-decoration:none;cursor:pointer}.secondary{background:#59636e}.muted{color:#68707a}.notice{border-left:4px solid #68707a;background:#f4f6f8;padding:12px 14px}.warning{border-left-color:#b7791f;background:#fff8e6}.actions{display:flex;gap:8px;flex-wrap:wrap}label{display:block;font-weight:700;margin:12px 0 5px}input{width:100%;padding:10px;border:1px solid #cfd4da;border-radius:7px}.row{display:grid;grid-template-columns:2fr 1fr;gap:14px}.row.three{grid-template-columns:1fr 1fr 1fr}table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;border-bottom:1px solid #e5e7eb;vertical-align:top}th{font-size:12px;color:#5d6670}.agency-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agency-nav a{display:inline-block;border:1px solid #cfd4da;border-radius:7px;background:#fff;color:#22272d;padding:8px 11px;text-decoration:none}.agency-nav a[aria-current='page']{background:#22272d;color:#fff;border-color:#22272d}.check{width:auto}.badge{display:inline-block;border-radius:999px;background:#eef1f4;padding:4px 8px;font-size:12px}@media(max-width:760px){.row,.row.three{grid-template-columns:1fr}table{display:block;overflow:auto}}
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

    def collect(self, *, tenant_id: str, session_id: str) -> _DiscoveryReviewBatch:
        with self._lock:
            batch = self._require(tenant_id=tenant_id, session_id=session_id)
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


def _clean_sector(observation: TraversalObservation) -> str:
    category = observation.business.category.strip()
    if not category or category.casefold() == observation.business.name.casefold():
        return ""
    if category.casefold() == "sponsored":
        return ""
    return category


def _prospect_for_ingest(observation: TraversalObservation):  # type: ignore[no-untyped-def]
    business = observation.business.model_copy(update={"category": _clean_sector(observation)})
    prospect = prospect_from_observation(business)
    evidence = (
        f"{prospect.evidence_summary}\nGoogle Maps discovery query: {observation.query_text}. "
        f"Result rank: {observation.result_rank}."
    )
    return prospect.model_copy(update={"evidence_summary": evidence[-4000:]})


def _review_table(observations: tuple[TraversalObservation, ...]) -> str:
    rows: list[str] = []
    for item in observations:
        business = item.business
        website = str(business.website) if business.website is not None else "—"
        source = str(business.source_url) if business.source_url is not None else ""
        selectable = business.website is not None
        checkbox = (
            f"<input class='check' type='checkbox' name='selected_rank' value='{item.result_rank}'>"
            if selectable
            else "<span class='muted'>No website</span>"
        )
        sector = _clean_sector(item) or "Unclassified"
        source_link = (
            f"<a href='{html.escape(source, quote=True)}' target='_blank' rel='noopener'>Maps</a>"
            if source
            else "—"
        )
        rows.append(
            "<tr>"
            f"<td>{checkbox}</td>"
            f"<td>{item.result_rank}</td>"
            f"<td><strong>{html.escape(business.name)}</strong><br><span class='muted'>{html.escape(sector)}</span></td>"
            f"<td>{html.escape(website)}</td>"
            f"<td>{source_link}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>Keep</th><th>Rank</th><th>Business</th><th>Website</th><th>Source</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


@router.get("", response_class=HTMLResponse)
def discovery_page(request: Request) -> str:
    identity = _identity(request)
    navigation = agency_navigation(identity, current="prospect-discovery")
    body = f"{navigation}<section><p><a href='/agency/prospects'>← Prospects</a></p><h1>Discover prospects</h1><p class='muted'>Open a bounded Google Maps search in visible Chromium. Nothing is saved until you review the captured businesses and explicitly select them.</p><form method='post' action='/agency/prospects/discover/start'><div class='row'><div><label for='query'>Search query</label><input id='query' name='query' maxlength='240' value='dentist in Vigo, ES' required></div><div><label for='country_code'>Country code</label><input id='country_code' name='country_code' maxlength='2' value='ES' required></div></div><div class='row'><div><label for='locality'>Locality</label><input id='locality' name='locality' maxlength='120' value='Vigo'></div><div><label for='administrative_area'>Administrative area</label><input id='administrative_area' name='administrative_area' maxlength='120' value='Pontevedra'></div></div><div class='row three'><div><label for='max_results'>Maximum results</label><input id='max_results' name='max_results' type='number' min='1' max='200' value='20'></div><div><label for='max_scrolls'>Maximum scrolls</label><input id='max_scrolls' name='max_scrolls' type='number' min='0' max='100' value='10'></div><div><label for='max_seconds'>Maximum seconds</label><input id='max_seconds' name='max_seconds' type='number' min='1' max='300' value='45'></div></div><button type='submit'>Open discovery browser</button></form></section>"
    return _page("Discover prospects", body)


@router.post("/start", response_model=None)
async def discovery_start(request: Request) -> HTMLResponse | RedirectResponse:
    identity = _identity(request)
    _trusted_origin(request)
    values = _values(await request.body())
    query = _one(values, "query")
    country_code = _one(values, "country_code").upper()
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
            locality=_one(values, "locality"),
            administrative_area=_one(values, "administrative_area"),
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
    body = f"{navigation}<section><h1>Browser opened</h1><p class='notice'>In the visible Chromium window, complete any normal Google sign-in/consent step and make sure the actual Maps result list for <strong>{html.escape(session.query_text)}</strong> is visible. Then return here and collect the bounded sample.</p><p class='muted'>Maximum {batch.limits.max_results} results · {batch.limits.max_scrolls} scrolls · {batch.limits.max_elapsed_seconds:g} seconds.</p><div class='actions'><form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/collect'><button type='submit'>Collect visible results</button></form><form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/cancel'><button class='secondary' type='submit'>Cancel</button></form></div></section>"
    return _page("Discovery browser ready", body)


@router.post("/{session_id}/collect", response_class=HTMLResponse)
def discovery_collect(session_id: str, request: Request) -> HTMLResponse:
    identity = _identity(request)
    _trusted_origin(request)
    try:
        batch = _REGISTRY.collect(tenant_id=identity.tenant_id, session_id=session_id)
    except (RuntimeError, ValueError) as exc:
        return HTMLResponse(
            _page("Discovery collection failed", f"<section><h1>Collection failed</h1><p class='muted'>{html.escape(str(exc))}</p><p><a href='/agency/prospects/discover'>Start another discovery</a></p></section>"),
            status_code=400,
        )
    navigation = agency_navigation(identity, current="prospect-discovery")
    selectable = sum(1 for item in batch.observations if item.business.website is not None)
    body = f"{navigation}<section><h1>Review discovered businesses</h1><p><strong>{len(batch.observations)}</strong> captured · <strong>{selectable}</strong> currently have a website and can be selected for the Webify prospect workbench.</p><p class='notice warning'>Nothing has been saved yet. Sponsored/no-website rows remain visible as evidence but cannot be ingested for website auditing.</p><form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/ingest'>{_review_table(batch.observations)}<p><button type='submit'>Ingest selected prospects</button></p></form><form method='post' action='/agency/prospects/discover/{html.escape(session_id, quote=True)}/cancel'><button class='secondary' type='submit'>Discard review</button></form></section>"
    return HTMLResponse(_page("Review discovered businesses", body))


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
            if item.result_rank in selected and item.business.website is not None
        )
        if not observations:
            raise ValueError("Select at least one discovered business with a website.")
        prospects = [_prospect_for_ingest(item) for item in observations]
        outcomes = TenantProspectDiscoveryIngestor(_root(request)).ingest(identity, prospects)
    except (TypeError, ValueError) as exc:
        return HTMLResponse(
            _page("Discovery ingest failed", f"<section><h1>Nothing was ingested</h1><p class='muted'>{html.escape(str(exc))}</p><p><a href='/agency/prospects/discover/{html.escape(session_id, quote=True)}'>Return to review</a></p></section>"),
            status_code=400,
        )
    finally:
        if 'outcomes' in locals():
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
        "<p class='notice'>Only the businesses you selected were processed. Existing human qualification, rejection, contact, audit and outreach state remains protected by the discovery ingest policy.</p>"
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