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
    return next((q.sector for q in study.queries if q.status != "captured"), None)


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


def geographic_overview(study: CityStudy) -> str:
    """Render a self-contained geographic scatter plot without external scripts.

    A static SVG is deliberate: the operator's strict Content Security Policy
    can prevent third-party map libraries and tiles from loading, leaving an
    otherwise empty box. Never pretend a Maps viewport centre is a place pin.
    """
    plotted: list[tuple[float, float, str, int, str]] = []
    for record in study.businesses:
        url = str(record.business.source_url or "")
        coordinate = _coordinates_from_maps_url(url)
        if coordinate is not None:
            plotted.append((
                coordinate[0], coordinate[1], record.business.name,
                record.score, url,
            ))
    missing = len(study.businesses) - len(plotted)
    if not plotted:
        return (
            "<section><h2>Opportunity map</h2><p>No verified business coordinates "
            "are available from the captured place links. Camera-centre values "
            "are intentionally excluded. The sector chart and opportunity "
            "table remain available below.</p></section>"
        )

    min_lat = min(point[0] for point in plotted)
    max_lat = max(point[0] for point in plotted)
    min_lon = min(point[1] for point in plotted)
    max_lon = max(point[1] for point in plotted)
    # Zero-range coordinates get a small margin rather than division by zero.
    lat_span = max(max_lat - min_lat, 0.002)
    lon_span = max(max_lon - min_lon, 0.002)
    width, height, margin = 960, 430, 34

    guides = "".join(
        f"<line x1='{margin}' y1='{margin + i * (height - 2 * margin) // 4}' "
        f"x2='{width - margin}' y2='{margin + i * (height - 2 * margin) // 4}' "
        "stroke='#395062' stroke-width='1' opacity='.55'/>"
        for i in range(5)
    )
    guides += "".join(
        f"<line x1='{margin + i * (width - 2 * margin) // 4}' y1='{margin}' "
        f"x2='{margin + i * (width - 2 * margin) // 4}' y2='{height - margin}' "
        "stroke='#395062' stroke-width='1' opacity='.55'/>"
        for i in range(5)
    )
    points: list[str] = []
    for lat, lon, name, score, url in plotted:
        x = margin + (lon - min_lon) / lon_span * (width - 2 * margin)
        y = height - margin - (lat - min_lat) / lat_span * (height - 2 * margin)
        if max_lon == min_lon:
            x = width / 2
        if max_lat == min_lat:
            y = height / 2
        safe_name = html.escape(name)
        safe_url = html.escape(url, quote=True)
        color = "#ec906f" if score >= 65 else "#58bdbf"
        points.append(
            f"<a href='{safe_url}' target='_blank' rel='noopener noreferrer'>"
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='6' fill='{color}' "
            "stroke='#091720' stroke-width='1.5'>"
            f"<title>{safe_name} · Discovery {score}/100</title>"
            "</circle></a>"
        )

    return (
        "<section><h2>Opportunity map</h2>"
        f"<p>{len(plotted)} businesses with place coordinates · "
        f"{missing} without verified place coordinates.</p>"
        "<p style='color:#9fb4c4'>Geographic position plot (north up, east right), "
        "not a street map or a ranking grid. Hover for the business name; "
        "click a point to open its original Google Maps record.</p>"
        "<svg role='img' aria-label='Geographic distribution of business opportunities' "
        f"viewBox='0 0 {width} {height}' "
        "style='display:block;width:100%;height:auto;max-height:440px;"
        "background:#172d3c;border:1px solid #304657;border-radius:12px'>"
        f"{guides}{''.join(points)}"
        "</svg><p style='color:#9fb4c4;font-size:13px'>"
        "<span style='color:#ec906f'>●</span> Discovery score ≥65&nbsp;&nbsp; "
        "<span style='color:#58bdbf'>●</span> Other candidates"
        "</p></section>"
    )



def market_detail(study: CityStudy) -> str:
    base = detail_url(study)
    pending = next_pending_sector(study)
    next_form = (
        f"<form method='post' action='{base}/start'>"
        f"<input type='hidden' name='sector' value='{html.escape(pending, quote=True)}'>"
        f"<button type='submit'>Continue with next sector: {html.escape(pending)}</button></form>"
        if pending is not None else "<p>All planned sectors have been captured.</p>"
    )
    sector_rows = "".join(
        f"<tr><td>{html.escape(q.sector)}</td><td>{html.escape(q.status)}</td>"
        f"<td>{q.captured}</td><td>"
        f"<form method='post' action='{base}/start'>"
        f"<input type='hidden' name='sector' value='{html.escape(q.sector, quote=True)}'>"
        f"<button type='submit'>Search in Maps</button></form></td></tr>"
        for q in study.queries
    )
    data = snapshot(study)
    numbers = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));"
        "gap:14px;margin:20px 0'>"
        "<div style='background:#172d3c;border:1px solid #355166;border-radius:12px;padding:18px'>"
        f"<strong style='display:block;font-size:30px'>{len(study.businesses)}</strong>"
        "<span>Unique businesses</span></div>"
        "<div style='background:#172d3c;border:1px solid #355166;border-radius:12px;padding:18px'>"
        f"<strong style='display:block;font-size:30px'>{data['coverage']['captured_queries']}/{len(study.queries)}</strong>"
        "<span>Queries completed</span></div>"
        "<div style='background:#172d3c;border:1px solid #355166;border-radius:12px;padding:18px'>"
        f"<strong style='display:block;font-size:30px'>{sum(r.score >= 65 for r in study.businesses)}</strong>"
        "<span>High discovery score</span></div></div>"
    )
    candidates = "".join(
        "<tr><td>" + html.escape(item.business.name) + "</td><td>"
        + html.escape(item.business.category) + "</td><td>" + str(item.score)
        + "/100</td><td>" + html.escape(", ".join(item.query_sectors))
        + "</td></tr>"
        for item in sorted(study.businesses, key=lambda r: -r.score)[:100]
    )
    analysis = html.escape(str((study.review or {}).get("summary", "Not reviewed yet")))
    return (
        "<section><p><a href='/agency/prospects/discover/market'>All market studies</a></p>"
        f"<h1>{html.escape(study.city)}, {html.escape(study.country_code)}</h1>"
        "<p>Directional market sample, not a business census. "
        "Open a search, collect its results, then attach the review to this study.</p>"
        f"{numbers}{next_form}</section>{geographic_overview(study)}{sector_chart(study)}<section><h2>Sector search plan</h2>"
        f"<table><tr><th>Sector</th><th>Status</th><th>Captured</th><th>Action</th></tr>{sector_rows}</table>"
        "</section><section><h2>Prioritized businesses</h2>"
        f"<table><tr><th>Business</th><th>Category</th><th>Discovery score</th><th>Seen in</th></tr>{candidates}</table></section>"
        f"<section><h2>AI market review</h2><p>{analysis}</p>"
        f"<p><a class='button' href='{base}/export'>Export JSON for ChatGPT</a> "
        f"<a class='button secondary' href='{base}/report'>Open visual report</a></p>"
        f"<form method='post' action='{base}/import-review'>"
        "<label>Paste AI review JSON</label><textarea name='review_json' rows='7' "
        "style='width:100%' required></textarea>"
        "<p><button type='submit'>Validate and import review</button></p>"
        "</form></section>"
    )


def input_json(study: CityStudy) -> bytes:
    value = snapshot(study)
    value["snapshot_sha256"] = snapshot_hash(study)
    return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
