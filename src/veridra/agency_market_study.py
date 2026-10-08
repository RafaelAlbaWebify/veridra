# ruff: noqa: E501
"""Operator-local Market Study navigation and storage. No automatic outreach."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

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


def market_detail(study: CityStudy) -> str:
    base = detail_url(study)
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
        f"<div class='cards'><div class='card'><strong>{len(study.businesses)}</strong>Unique businesses</div>"
        f"<div class='card'><strong>{data['coverage']['captured_queries']}/{len(study.queries)}</strong>Queries completed</div>"
        f"<div class='card'><strong>{sum(r.score >= 65 for r in study.businesses)}</strong>High discovery score</div></div>"
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
        f"{numbers}</section><section><h2>Sector search plan</h2>"
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
