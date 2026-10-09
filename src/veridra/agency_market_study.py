# ruff: noqa: E501
"""Operator-local Market Study navigation and storage. No automatic outreach."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import unquote

from .market_intelligence import CityStudy, load, save, snapshot, snapshot_hash


def study_root(root: Path, tenant_id: str) -> Path:
    return root / "_market_studies" / hashlib.sha256(tenant_id.encode()).hexdigest()


def study_path(root: Path, tenant_id: str, study_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", study_id):
        raise ValueError("Invalid study identifier")
    return study_root(root, tenant_id) / f"{study_id}.json"


def all_studies(root: Path, tenant_id: str) -> list[CityStudy]:
    directory = study_root(root, tenant_id)
    return sorted(
        (load(path) for path in directory.glob("*.json")),
        key=lambda s: s.created_at,
        reverse=True,
    )


def store_study(root: Path, tenant_id: str, study: CityStudy) -> None:
    path = study_path(root, tenant_id, study.study_id)
    save(study, path)


def detail_url(study: CityStudy) -> str:
    return f"/agency/prospects/discover/market/{study.study_id}"


def market_overview(root: Path, tenant_id: str) -> str:
    rows = "".join(
        "<tr><td><a href='" + detail_url(s) + "'>" + html.escape(s.city) + ", "
        + html.escape(s.country_code) + "</a></td><td>" + str(len(s.queries))
        + "</td><td>" + str(len(s.businesses)) + "</td></tr>"
        for s in all_studies(root, tenant_id)
    )
    return (
        "<section><h1>City Market Intelligence</h1>"
        "<p>Create a city-wide multisector research plan. Each Google Maps search "
        "remains operator-supervised. No contact is sent automatically.</p>"
        "<form method='post' action='/agency/prospects/discover/market/new'>"
        "<label>City <input name='city' required maxlength='160' placeholder='Galway'></label>"
        "<label>Country code <input name='country' required maxlength='2' value='IE'></label>"
        "<label>Business sectors (optional; comma separated)"
        "<input name='sectors' placeholder='Use recommended broad sector set'></label>"
        "<button type='submit'>Create market study</button></form></section>"
        "<section><h2>Saved studies</h2><table><tr><th>Market</th>"
        f"<th>Planned queries</th><th>Candidates</th></tr>{rows}</table></section>"
    )


def next_pending_sector(study: CityStudy) -> str | None:
    return next((q.sector for q in study.queries if q.sector == study.batch_queue[0] and q.active), None) if study.batch_queue else next((q.sector for q in study.queries if q.status != "captured" and q.active), None)


def sector_chart(study: CityStudy) -> str:
    counts = {q.sector: sum(q.sector in r.query_sectors for r in study.businesses) for q in study.queries}
    maximum = max(counts.values(), default=0) or 1
    rows = "".join(
        "<div style='display:grid;grid-template-columns:140px 1fr 45px;gap:12px;align-items:center;margin:9px 0'>"
        f"<span>{html.escape(sector)}</span>"
        f"<div style='background:#243645;height:19px;border-radius:5px;overflow:hidden'>"
        f"<div style='height:100%;width:{count * 100 / maximum:.1f}%;background:#3ea9b8'></div></div>"
        f"<strong>{count}</strong></div>"
        for sector, count in sorted(counts.items(), key=lambda x: -x[1])
    )
    return (
        "<section><h2>Sector coverage</h2>"
        "<p>Observed candidates per sector, not an estimate of the whole market.</p>"
        + rows + "</section>"
    )



def _coordinates_from_maps_url(url: str) -> tuple[float, float] | None:
    """Only extract place-point coordinates, never the Maps camera position.

    The @lat,lon portion of a Google Maps URL denotes the viewport centre and
    cannot safely be treated as the location of an individual business.
    """
    value = unquote(url)
    match = re.search(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)", value)
    if match is None:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def map_points(study: CityStudy) -> list[dict[str, object]]:
    """Observed Google Maps place positions, never viewport centres."""
    points: list[dict[str, object]] = []
    for record in study.businesses:
        url = str(record.business.source_url or "")
        coordinate = _coordinates_from_maps_url(url)
        if coordinate is None:
            continue
        points.append({
            "lat": coordinate[0],
            "lon": coordinate[1],
            "name": record.business.name,
            "score": record.score,
            "url": url,
        })
    return points


def geographic_overview(study: CityStudy) -> str:
    """Embed a same-origin Leaflet view with an actual street-map baselayer."""
    points = map_points(study)
    missing = len(study.businesses) - len(points)
    if not points:
        return (
            "<section><h2>Opportunity map</h2><p>No verified business coordinates "
            "are available from captured place links.</p></section>"
        )
    source = f"{detail_url(study)}/map-view"
    return (
        "<section><h2>Opportunity map</h2>"
        f"<p>{len(points)} businesses with place coordinates · "
        f"{missing} without verified place coordinates.</p>"
        f"<p><a href='{html.escape(source, quote=True)}' target='_blank' rel='noopener'>Open map in new tab</a></p>"
        "<p>Street map with zoom and clickable business markers. "
        "Cartography © OpenStreetMap contributors.</p>"
        f"<iframe title='Interactive map of {html.escape(study.city, quote=True)} businesses' "
        f"src='{html.escape(source, quote=True)}' "
        "loading='lazy' referrerpolicy='no-referrer' "
        "style='width:100%;height:490px;background:#172d3c;"
        "border:1px solid #304657;border-radius:12px'></iframe>"
        "</section>"
    )



def market_detail(study: CityStudy) -> str:
    """One-screen operator cockpit; details are expandable, never a tall report."""
    base = detail_url(study)
    pending = next_pending_sector(study)
    ranked = sorted(study.businesses, key=lambda r: (-r.score, r.business.name.casefold()))
    high_count = sum(r.score >= 65 for r in study.businesses)
    positioned = len(map_points(study))
    completed = sum(q.status == "captured" for q in study.queries)
    safe_city = html.escape(study.city)
    safe_country = html.escape(study.country_code)
    next_form = (
        f"<form method='post' action='{base}/start'>"
        f"<input type='hidden' name='sector' value='{html.escape(pending, quote=True)}'>"
        f"<button class='market-next' type='submit'>Continue: {html.escape(pending)} →</button></form>"
        if pending else "<span class='market-finished'>All sectors complete</span>"
    )

    sectors = "".join(
        "<div class='market-sector-row" + (" active" if q.status == "captured" else "") + "'>"
        f"<input form='market-bulk' type='checkbox' name='sector' value='{html.escape(q.sector, quote=True)}' aria-label='Select {html.escape(q.sector, quote=True)}'>"
        f"<span class='market-sector-name' title='{html.escape(q.sector, quote=True)}'>{html.escape(q.sector)}</span>"
        f"<span class='market-sector-state'>{'inactive' if not q.active else html.escape(q.status)}</span>"
        f"<strong>{q.captured}</strong>"
        f"<form method='post' action='{base}/start'>"
        f"<input type='hidden' name='sector' value='{html.escape(q.sector, quote=True)}'>"
        f"<button type='submit' {'disabled' if not q.active else ''}>{'Repeat' if q.status == 'captured' else 'Search'}</button></form></div>"
        for q in study.queries
    )
    top = "".join(
        "<tr><td><a href='" + html.escape(str(r.business.source_url or "#"), quote=True)
        + "' target='_blank' rel='noopener noreferrer'>"
        + html.escape(r.business.name) + "</a></td><td>"
        + html.escape(r.business.category) + "</td><td><strong>"
        + str(r.score) + "/100</strong></td></tr>"
        for r in ranked[:8]
    )
    full = "".join(
        "<tr><td><a href='" + html.escape(str(r.business.source_url or "#"), quote=True)
        + "' target='_blank' rel='noopener noreferrer'>"
        + html.escape(r.business.name) + "</a></td><td>"
        + html.escape(r.business.category) + "</td><td>" + str(r.score)
        + "/100</td><td>" + html.escape(", ".join(r.query_sectors))
        + "</td></tr>"
        for r in ranked
    )
    analysis = html.escape(str((study.review or {}).get("summary", "No review imported yet.")))
    editors = "".join(
        f"<form class='market-editor' method='post' action='{base}/manage'>"
        f"<input type='hidden' name='action' value='edit'>"
        f"<input type='hidden' name='edit_sector' value='{html.escape(q.sector, quote=True)}'>"
        f"<strong>{html.escape(q.sector)}</strong>"
        f"<input aria-label='Search query for {html.escape(q.sector, quote=True)}' type='text' name='query_text' maxlength='300' value='{html.escape(q.query_text, quote=True)}' required>"
        f"<label><input type='checkbox' name='active' {'checked' if q.active else ''}>Active</label>"
        "<button type='submit'>Save</button></form>"
        for q in study.queries
    )

    if positioned:
        map_markup = (
            f"<iframe title='Interactive business map of {html.escape(study.city, quote=True)}' "
            f"src='{base}/map-view' loading='lazy' referrerpolicy='no-referrer'></iframe>"
        )
    else:
        map_markup = (
            "<p class='market-no-map'>No verified place coordinates available. "
            "Use the sector and candidate lists to continue research.</p>"
        )
    css = """
<style>
.market-workbench{--mp:#112737;--mb:#2d4b5d;--mt:#e3eff8;--mm:#b1c6d5;color:var(--mt);
 font:14px/1.45 system-ui,'Segoe UI',sans-serif;max-width:none;width:100%}
.market-workbench *{box-sizing:border-box}
.market-workbench{position:relative}
.market-workbench a{color:#a7ddf3}
.market-workbench button,.market-workbench .market-button{
 font:600 13px/1.3 system-ui,'Segoe UI',sans-serif;min-height:33px;padding:7px 11px;
 border:1px solid #3b6379;border-radius:7px;background:#153a52;color:#edf7ff;cursor:pointer}
.market-workbench button:hover,.market-workbench .market-button:hover{background:#22546e}
.market-head{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap}
.market-title{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.market-title h1{font:700 25px/1.2 system-ui,'Segoe UI',sans-serif;margin:0}
.market-subtitle{font-size:13px;color:var(--mm);margin:0}
.market-kpis{display:flex;gap:9px;align-items:stretch;margin-bottom:12px;flex-wrap:wrap}
.market-stat{background:var(--mp);border:1px solid var(--mb);border-radius:9px;
 padding:9px 13px;flex:1 1 125px;min-width:120px}
.market-stat strong{display:block;font-size:23px;line-height:1.1}
.market-stat span{font-size:13px;color:var(--mm)}
.market-next-slot{flex:2 1 200px;display:flex;align-items:center;justify-content:flex-end;gap:10px}
.market-next-slot form{margin:0}
.market-next-slot .market-next{background:#086293;border-color:#3682ac;font-size:14px}
.market-grid{display:grid;grid-template-columns:minmax(245px,23fr) minmax(380px,48fr) minmax(250px,29fr);
 gap:12px;min-height:0;height:clamp(390px,54vh,620px)}
.market-panel{background:var(--mp);border:1px solid var(--mb);border-radius:10px;
 min-width:0;min-height:0;display:flex;flex-direction:column;overflow:hidden}
.market-panel-head{display:flex;align-items:center;justify-content:space-between;
 padding:11px 12px;gap:8px;border-bottom:1px solid var(--mb);flex-shrink:0}
.market-panel-head h2{font:650 17px/1.2 system-ui,'Segoe UI',sans-serif;margin:0}
.market-panel-head small{font-size:13px;color:var(--mm)}
.market-panel-scroll{overflow:auto;min-height:0;flex:1}
.market-sector-row{display:grid;grid-template-columns:18px minmax(0,1fr) 65px 25px 60px;
 align-items:center;gap:6px;border-bottom:1px solid #274253;padding:6px 9px;font-size:13px}
.market-sector-row.active{background:#173a50}
.market-sector-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}
.market-sector-state{color:#a9c5d7;font-size:12px}
.market-sector-row strong{text-align:right;font-size:13px}
.market-sector-row form{margin:0}
.market-sector-row input[type=checkbox]{width:16px;height:16px;min-width:16px;margin:0;accent-color:#3ea9b8}
.market-bulk-bar{display:flex;gap:6px;flex-wrap:wrap;padding:8px;border-top:1px solid var(--mb)}
.market-bulk-bar button{font-size:12px;min-height:30px;padding:5px 7px}
.market-editor{display:grid;grid-template-columns:minmax(115px,1fr) minmax(260px,2fr) auto auto;gap:9px;align-items:center;margin:8px 0}
.market-editor input[type=text]{width:100%;font:14px system-ui;padding:6px;background:#0e2030;color:#edf7ff;border:1px solid #496477;border-radius:6px}
.market-editor input[type=checkbox]{width:16px;height:16px}
.market-editor label{font-size:13px}
@media(max-width:740px){.market-editor{grid-template-columns:1fr}}
.market-sector-row button{padding:5px;min-height:28px;font-size:12px;width:100%}
.market-map-toolbar{gap:8px}
.market-map-toolbar a{font-size:13px}
.market-map-area{flex:1;min-height:0;background:#183243}
.market-map-area iframe{display:block;width:100%;height:100%;border:0}
.market-no-map{padding:18px;font-size:14px}
.market-panel table{border-collapse:collapse;width:100%;font-size:13px}
.market-panel th{position:sticky;top:0;background:#102432;text-align:left;color:var(--mm);font-size:12px}
.market-panel th,.market-panel td{padding:9px 10px;border-bottom:1px solid #284254}
.market-panel td:first-child{font-size:14px}
.market-panel td:last-child{white-space:nowrap}
.market-bottom{margin-top:12px;background:var(--mp);border:1px solid var(--mb);
 border-radius:10px;min-height:0}
.market-bottom>summary{cursor:pointer;padding:11px 14px;font-size:14px;font-weight:650}
.market-bottom[open]{position:absolute;inset:103px 0 0;z-index:10;display:flex;flex-direction:column;box-shadow:0 14px 45px #000b;background:#0f2534;overflow:hidden}
.market-bottom[open]>summary{border-bottom:1px solid var(--mb);flex-shrink:0}
.market-bottom[open] .market-tabs{flex-shrink:0}
.market-bottom[open] .market-tab-panels{flex:1;min-height:0;overflow:hidden}
.market-bottom[open] .market-detail-block{height:100%;overflow:auto}
.market-bottom[open] .market-table-scroll{max-height:none;height:calc(100% - 45px)}
.market-tabs input{position:absolute;opacity:0;width:1px;height:1px}
.market-tabs label{cursor:pointer;padding:7px 12px;border:1px solid #355267;border-radius:7px;font-size:14px;color:#c1d6e4}
.market-bottom:has(#market-tab-businesses:checked) label[for=market-tab-businesses],
.market-bottom:has(#market-tab-coverage:checked) label[for=market-tab-coverage],
 .market-bottom:has(#market-tab-review:checked) label[for=market-tab-review],
.market-bottom:has(#market-tab-edit:checked) label[for=market-tab-edit]{background:#21516c;color:#fff}
.market-bottom .market-detail-block{display:none}
.market-bottom:has(#market-tab-businesses:checked) #market-businesses,
.market-bottom:has(#market-tab-coverage:checked) #market-coverage,
.market-bottom:has(#market-tab-review:checked) #market-review,
.market-bottom:has(#market-tab-edit:checked) #market-edit{display:block}
.market-tabs{display:flex;flex-wrap:wrap;gap:7px;padding:10px}
.market-tabs a{padding:7px 12px;border:1px solid #355267;border-radius:7px;font-size:13px}
.market-detail-block{padding:11px 14px;border-top:1px solid #264254}
.market-detail-block h3{font-size:16px;margin:4px 0 10px}
.market-detail-block table{width:100%;border-collapse:collapse;font-size:13px}
.market-detail-block th,.market-detail-block td{padding:7px;text-align:left;border-bottom:1px solid #2d4557}
.market-table-scroll{max-height:290px;overflow:auto}
.market-workbench textarea{font:14px/1.5 system-ui,'Segoe UI',sans-serif;width:100%;min-height:110px}
.market-detail-block form{margin:8px 0}
@media(min-width:1100px) and (min-height:700px){
 .market-workbench{height:calc(100dvh - 186px);min-height:520px;display:flex;flex-direction:column}
 .market-grid{flex:1;height:auto;min-height:0}
}
@media(max-width:1100px){
 .market-grid{grid-template-columns:minmax(210px,32fr) minmax(340px,68fr);
 height:clamp(410px,65vh,700px)}
 .market-priorities{grid-column:1/-1;max-height:230px}
}
@media(max-width:740px){
 .market-bottom[open]{position:fixed;inset:90px 8px 8px}
 .market-grid{display:flex;flex-direction:column;height:auto}
 .market-sector-plan{height:230px}
 .market-map{height:380px}
 .market-priorities{height:230px}
 .market-workbench{height:auto}
 .market-next-slot{justify-content:flex-start}
}
</style>
"""
    return (
        css + "<div class='market-workbench'>"
        "<header class='market-head'><div class='market-title'>"
        f"<h1>{safe_city}, {safe_country}</h1>"
        "<p class='market-subtitle'>Market study · Sample-based discovery, not a census</p></div>"
        "<a href='/agency/prospects/discover/market'>All studies</a></header>"
        "<div class='market-kpis'>"
        f"<div class='market-stat'><strong>{len(study.businesses)}</strong><span>Businesses</span></div>"
        f"<div class='market-stat'><strong>{completed}/{len(study.queries)}</strong><span>Sectors completed</span></div>"
        f"<div class='market-stat'><strong>{high_count}</strong><span>High discovery score</span></div>"
        f"<div class='market-stat'><strong>{len(study.businesses)-positioned}</strong><span>Missing coordinates</span></div>"
        f"<div class='market-next-slot'>{next_form}</div></div>"
        "<div class='market-grid'>"
        "<section class='market-panel market-sector-plan'>"
        f"<div class='market-panel-head'><h2>Sector plan</h2><small>{completed}/{len(study.queries)} completed</small></div>"
        f"<div class='market-panel-scroll'>{sectors}</div>"
        f"<form id='market-bulk' class='market-bulk-bar' method='post' action='{base}/manage'>"
        "<button name='action' value='queue_all' type='submit'>Queue all</button>"
        "<button name='action' value='queue' type='submit'>Queue selected</button>"
        "<button name='action' value='activate' type='submit'>Enable</button>"
        "<button name='action' value='deactivate' type='submit'>Disable</button>"
        "<button name='action' value='remove' type='submit' title='Remove chosen searches from plan, keeping all existing businesses'>Remove</button>"
        "</form></section>"
        "<section class='market-panel market-map'>"
        "<div class='market-panel-head market-map-toolbar'><h2>Opportunity map</h2>"
        f"<small>{positioned} positioned</small>"
        f"<a href='{base}/map-view' target='_blank' rel='noopener'>Full map ↗</a></div>"
        f"<div class='market-map-area'>{map_markup}</div></section>"
        "<section class='market-panel market-priorities'>"
        f"<div class='market-panel-head'><h2>Prioritized businesses</h2><small>Top {min(8,len(ranked))}</small></div>"
        "<div class='market-panel-scroll'><table><thead><tr><th>Business</th>"
        f"<th>Category</th><th>Score</th></tr></thead><tbody>{top}</tbody></table></div></section>"
        "</div>"
        "<details class='market-bottom'><summary>Businesses, coverage &amp; AI review — expand details</summary>"
        "<nav class='market-tabs' aria-label='Market study details'>"
        "<input type='radio' name='market-tab' id='market-tab-businesses' checked>"
        "<label for='market-tab-businesses'>Businesses</label>"
        "<input type='radio' name='market-tab' id='market-tab-coverage'>"
        "<label for='market-tab-coverage'>Coverage</label>"
        "<input type='radio' name='market-tab' id='market-tab-review'>"
        "<label for='market-tab-review'>AI review</label>"
        "<input type='radio' name='market-tab' id='market-tab-edit'>"
        "<label for='market-tab-edit'>Edit searches</label></nav><div class='market-tab-panels'>"
        "<div class='market-detail-block' id='market-businesses'><h3>All observed businesses</h3>"
        "<div class='market-table-scroll'><table><thead><tr><th>Business</th><th>Category</th>"
        f"<th>Discovery score</th><th>Seen in</th></tr></thead><tbody>{full}</tbody></table></div></div>"
        f"<div class='market-detail-block' id='market-coverage'>{sector_chart(study)}</div>"
        "<div class='market-detail-block' id='market-review'><h3>AI strategic review</h3>"
        f"<p>{analysis}</p><p><a href='{base}/export'>Export JSON for ChatGPT</a> · "
        f"<a href='{base}/report'>Open visual report</a></p>"
        f"<form method='post' action='{base}/import-review'>"
        "<label>Paste AI review JSON<textarea name='review_json' required></textarea></label>"
        "<button type='submit'>Validate and import review</button></form></div>"
        f"<div class='market-detail-block' id='market-edit'><h3>Edit search plan</h3>{editors}"
        f"<form class='market-editor' action='{base}/manage' method='post'>"
        "<input type='hidden' name='action' value='add'>"
        "<input type='text' name='edit_sector' placeholder='New sector' maxlength='100' required>"
        "<input type='text' name='query_text' placeholder='Search terms and city' maxlength='300' required>"
        "<label><input type='checkbox' name='active' checked>Active</label>"
        "<button type='submit'>Add</button></form>"
        f"<form method='post' action='{base}/manage'>"
        "<button type='submit' name='action' value='clear_queue'>Clear batch queue</button>"
        "</form></div>"
        "</div></details></div>"
    )


def input_json(study: CityStudy) -> bytes:
    value = snapshot(study)
    value["snapshot_sha256"] = snapshot_hash(study)
    return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
