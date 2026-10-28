"""Private operator Website Care history view, read-only and opt-in."""
from __future__ import annotations

import html
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from .website_care_history import read_history

router = APIRouter(prefix="/agency/website-care", tags=["website-care"])


def _configured_db() -> Path | None:
    raw = os.getenv("VERIDRA_WEBSITE_CARE_DB", "").strip()
    return Path(raw) if raw else None


@router.get("/history", response_class=HTMLResponse)
def website_care_history_page(
    website_ref: str | None = Query(default=None, min_length=1, max_length=128),
) -> str:
    db = _configured_db()
    if db is None:
        return (
            "<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<title>Website Care</title><main><h1>Website Care</h1>"
            "<p>Evidence ledger not configured. Set VERIDRA_WEBSITE_CARE_DB "
            "to a private local SQLite file and import validated evidence first.</p>"
            "</main></html>"
        )
    try:
        runs = read_history(db, website_ref=website_ref, limit=50)
    except (ValueError, sqlite3.DatabaseError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Website Care ledger unavailable") from exc
    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(run["website_ref"])),
            html.escape(str(run["platform"])),
            html.escape(str(run["finished_utc"])),
            "PASS" if run["passed"] else "FAIL",
            html.escape(str(run["recovery_tested"])),
        )
        for run in runs
    )
    if not rows:
        rows = "<tr><td colspan='5'>No validated maintenance evidence yet.</td></tr>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Website Care · VERIDRA</title>"
        "<style>body{font:14px Arial,sans-serif;max-width:1000px;margin:36px auto;"
        "padding:0 18px;color:#24292f}table{border-collapse:collapse;width:100%}"
        "td,th{border-bottom:1px solid #ddd;text-align:left;padding:10px}"
        "th{background:#f5f5f5}</style></head><body>"
        "<main><h1>Website Care · maintenance history</h1>"
        "<p>Local operator evidence only. No updates or remote actions occur here.</p>"
        "<table><thead><tr><th>Website</th><th>Platform</th><th>Finished (UTC)</th>"
        "<th>Result</th><th>Recovery test</th></tr></thead><tbody>"
        + rows + "</tbody></table></main></body></html>"
    )
