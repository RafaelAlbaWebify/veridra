# ruff: noqa: E501
"""Local-first city studies: persistent market intelligence, not CRM outreach."""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .prospect_discovery import ObservedBusiness
from .prospect_opportunity import assess_opportunity

DEFAULT_SECTORS = (
    "dentist", "physiotherapist", "accountant", "solicitor",
    "estate agent", "architect", "veterinarian", "optician",
    "auto repair", "hotel", "restaurant", "beauty salon",
)


class MarketQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sector: str = Field(min_length=1, max_length=100)
    query_text: str = Field(min_length=1, max_length=300)
    status: str = "planned"
    captured: int = 0
    active: bool = True
    query_history: list[str] = Field(default_factory=list)


class MarketRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_id: str
    business: ObservedBusiness
    query_sectors: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    score: int
    confidence: str = "medium"


class CityStudy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    study_id: str = Field(default_factory=lambda: uuid4().hex)
    city: str = Field(min_length=1, max_length=160)
    country_code: str = Field(min_length=2, max_length=2)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    queries: list[MarketQuery] = Field(default_factory=list)
    businesses: list[MarketRecord] = Field(default_factory=list)
    review: dict[str, Any] | None = None
    batch_queue: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_country(self) -> CityStudy:
        self.country_code = self.country_code.upper()
        if len(self.country_code) != 2:
            raise ValueError("Country code must have two letters")
        return self


def plan(city: str, country: str, sectors: tuple[str, ...] = DEFAULT_SECTORS) -> CityStudy:
    study = CityStudy(city=city, country_code=country)
    unique = dict.fromkeys(s.strip().lower() for s in sectors if s.strip())
    study.queries = [
        MarketQuery(sector=s, query_text=f"{s} in {study.city}, {study.country_code}")
        for s in unique
    ]
    return study


def manage_queries(
    study: CityStudy, action: str, sectors: list[str],
    *, sector: str = "", query_text: str = "", active: bool = True,
) -> CityStudy:
    """Edit the search plan while preserving all observed business records."""
    updated = study.model_copy(deep=True)
    chosen = set(sectors)
    existing = {q.sector: q for q in updated.queries}
    if action == "queue":
        if not chosen or not chosen.issubset(existing):
            raise ValueError("Select valid sectors")
        updated.batch_queue = [
            q.sector for q in updated.queries if q.sector in chosen and q.active
        ]
        if not updated.batch_queue:
            raise ValueError("Selected searches are inactive")
    elif action in {"activate", "deactivate"}:
        if not chosen or not chosen.issubset(existing):
            raise ValueError("Select valid sectors")
        for q in updated.queries:
            if q.sector in chosen:
                q.active = action == "activate"
        updated.batch_queue = [s for s in updated.batch_queue if existing[s].active]
    elif action == "edit":
        target = existing.get(sector)
        if target is None:
            raise ValueError("Unknown sector")
        value = query_text.strip()
        if not value or len(value) > 300:
            raise ValueError("Query must contain 1–300 characters")
        if value != target.query_text:
            target.query_history.append(target.query_text)
            target.query_text = value
            target.status = "planned"
            target.captured = 0
            updated.batch_queue = [s for s in updated.batch_queue if s != sector]
        target.active = active
    elif action == "add":
        name = sector.strip().lower()
        value = query_text.strip()
        if not name or len(name) > 100 or name in existing:
            raise ValueError("New sector name is empty, too long or duplicated")
        if not value or len(value) > 300:
            raise ValueError("Query must contain 1–300 characters")
        updated.queries.append(MarketQuery(sector=name, query_text=value, active=active))
    elif action == "remove":
        if not chosen or not chosen.issubset(existing):
            raise ValueError("Select valid sectors")
        updated.queries = [q for q in updated.queries if q.sector not in chosen]
        updated.batch_queue = [s for s in updated.batch_queue if s not in chosen]
    elif action == "clear_queue":
        updated.batch_queue = []
    else:
        raise ValueError("Unsupported search management action")
    updated.review = None
    return updated


def _business_identity(business: ObservedBusiness) -> tuple[str, str]:
    key = business.provider_key.strip()
    if key and not key.startswith("google-maps:") and not key.startswith("name:"):
        return ("medium", f"{business.provider.lower()}:{key.lower()}")
    if key.startswith("google-maps:") and business.source_url is not None:
        return ("high", f"{business.provider.lower()}:{key.lower()}")
    site = str(business.website or "").lower().rstrip("/")
    name = re.sub(r"\s+", " ", business.name.casefold().strip())
    city = business.locality.casefold()
    # Do not automatically unify different names just because they share a website.
    return ("low", f"fallback:{name}:{city}:{business.country_code.lower()}:{site}")


def add_observations(
    study: CityStudy, sector: str, businesses: list[ObservedBusiness]
) -> CityStudy:
    if sector not in {query.sector for query in study.queries}:
        raise ValueError("Sector is not in this study plan")
    # Revalidate before modification and keep CRM entirely separate.
    updated = study.model_copy(deep=True)
    indexed: dict[str, int] = {r.business_id: i for i, r in enumerate(updated.businesses)}
    for business in businesses:
        if business.country_code.upper() != updated.country_code:
            raise ValueError("Observation country does not match study")
        confidence, identity = _business_identity(business)
        stable_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        if stable_id in indexed:
            record = updated.businesses[indexed[stable_id]]
            if sector not in record.query_sectors:
                record.query_sectors.append(sector)
            if str(business.source_url or "") not in record.sources:
                record.sources.append(str(business.source_url or ""))
            if business.website is not None and record.business.website is None:
                record.business = business
                record.score = assess_opportunity(business).score
        else:
            record = MarketRecord(
                business_id=stable_id,
                business=business,
                query_sectors=[sector],
                sources=[str(business.source_url or "")],
                score=assess_opportunity(business).score,
                confidence=confidence,
            )
            indexed[stable_id] = len(updated.businesses)
            updated.businesses.append(record)
    for query in updated.queries:
        if query.sector == sector:
            query.status = "captured"
            query.captured = len(businesses)
    updated.review = None  # invalidate stale strategic judgment
    return updated


def snapshot(study: CityStudy) -> dict[str, Any]:
    counts = Counter(
        sector for record in study.businesses for sector in record.query_sectors
    )
    return {
        "schema_version": "1.0",
        "contract": "veridra_market_review_input",
        "study_id": study.study_id,
        "city": study.city,
        "country_code": study.country_code,
        "coverage": {
            "planned_queries": len(study.queries),
            "captured_queries": sum(q.status == "captured" for q in study.queries),
            "unique_businesses": len(study.businesses),
            "not_a_census": True,
        },
        "sectors": [
            {"sector": query.sector, "status": query.status, "observed_businesses": counts[query.sector]}
            for query in study.queries
        ],
        "candidates": [
            {
                "business_id": r.business_id,
                "name": r.business.name,
                "sector": r.business.category,
                "sectors": r.query_sectors,
                "website": str(r.business.website or ""),
                "score": r.score,
                "identity_confidence": r.confidence,
            }
            for r in study.businesses
        ],
    }


def snapshot_hash(study: CityStudy) -> str:
    return hashlib.sha256(
        json.dumps(snapshot(study), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def import_review(study: CityStudy, review: dict[str, Any]) -> CityStudy:
    if review.get("contract") != "veridra_market_review_output":
        raise ValueError("Unexpected review contract")
    if review.get("schema_version") != "1.0":
        raise ValueError("Unsupported review schema")
    if review.get("study_id") != study.study_id:
        raise ValueError("Review belongs to a different study")
    if review.get("snapshot_sha256") != snapshot_hash(study):
        raise ValueError("Review is stale")
    allowed = {"contract", "schema_version", "study_id", "snapshot_sha256", "sector_priorities", "candidate_priorities", "summary"}
    if set(review) - allowed:
        raise ValueError("Unexpected fields in review")
    sectors = {q.sector for q in study.queries}
    ids = {r.business_id for r in study.businesses}
    if not isinstance(review.get("summary"), str) or len(review["summary"]) > 5000:
        raise ValueError("Review summary must be bounded text")
    for field, name_key, valid in (("sector_priorities", "sector", sectors), ("candidate_priorities", "business_id", ids)):
        entries = review.get(field, [])
        if not isinstance(entries, list) or len(entries) > 1000:
            raise ValueError("Invalid priorities")
        for item in entries:
            if not isinstance(item, dict) or set(item) != {name_key, "priority", "reason"}:
                raise ValueError("Invalid priority item")
            if item[name_key] not in valid or not isinstance(item["priority"], int) or not 0 <= item["priority"] <= 100:
                raise ValueError("Unknown target or invalid priority")
            if not isinstance(item["reason"], str) or len(item["reason"]) > 1000:
                raise ValueError("Invalid reasoning")
    updated = study.model_copy(deep=True)
    updated.review = review
    return updated


def save(study: CityStudy, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(study.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)


def load(path: Path) -> CityStudy:
    return CityStudy.model_validate_json(path.read_text(encoding="utf-8"))


def dashboard(study: CityStudy) -> str:
    data = snapshot(study)
    ranked = sorted(study.businesses, key=lambda r: (-r.score, r.business.name))
    sector_rows = "".join(
        f"<tr><td>{html.escape(s['sector'])}</td><td>{s['observed_businesses']}</td><td>{html.escape(s['status'])}</td></tr>"
        for s in data["sectors"]
    )
    rows = "".join(
        f"<tr><td>{html.escape(r.business.name)}</td><td>{html.escape(r.business.category)}</td>"
        f"<td>{r.score}/100</td><td>{html.escape(r.confidence)}</td></tr>"
        for r in ranked
    )
    review_text = html.escape(str((study.review or {}).get("summary", "Not yet reviewed")))
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<title>VERIDRA · Market Intelligence</title><style>"
        "body{background:#0f1720;color:#e7eef7;font:15px system-ui;margin:0;padding:32px}"
        "main{max-width:1200px;margin:auto}h1{margin-bottom:4px}.muted{color:#9aadc0}"
        ".cards{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.card{background:#172633;border:1px solid #304154;"
        "border-radius:12px;padding:20px;flex:1;min-width:160px}.card strong{font-size:28px;display:block}"
        "table{border-collapse:collapse;width:100%;margin-bottom:30px}td,th{text-align:left;padding:11px;"
        "border-bottom:1px solid #304154}th{color:#afbed1}section{overflow:auto}small{color:#aab8c9}"
        "</style><main><h1>VERIDRA · City Market Intelligence</h1>"
        f"<p class='muted'>{html.escape(study.city)}, {html.escape(study.country_code)} · Preliminary sample, not a census</p>"
        "<div class='cards'>"
        f"<div class='card'><strong>{len(study.businesses)}</strong>Unique candidates</div>"
        f"<div class='card'><strong>{data['coverage']['captured_queries']}/{len(study.queries)}</strong>Queries captured</div>"
        f"<div class='card'><strong>{sum(r.score >= 65 for r in study.businesses)}</strong>High-score candidates</div>"
        "</div><section><h2>Sectors</h2><table><tr><th>Sector</th><th>Candidates</th><th>Coverage</th></tr>"
        f"{sector_rows}</table></section><section><h2>Opportunities</h2>"
        "<table><tr><th>Business</th><th>Category</th><th>Discovery score</th><th>Identity confidence</th></tr>"
        f"{rows}</table></section><section><h2>AI strategic review</h2><p>{review_text}</p></section></main></html>"
    )
