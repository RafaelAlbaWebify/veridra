from __future__ import annotations

import html
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from .collector import CollectionError
from .core import Assessment, UnsafeTargetError, demo_assessment
from .history import HistoryError, HistoryStore
from .service import assess_url

router = APIRouter()


def _store() -> HistoryStore:
    return HistoryStore()


def _resolve(url: str | None, demo: bool) -> Assessment:
    if demo:
        return demo_assessment()
    if url is None:
        raise HTTPException(status_code=400, detail="A target URL is required.")
    try:
        return assess_url(url)
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _page(title: str, body: str) -> str:
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{escaped_title} · Veridra</title>
<style>
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: #f7f8fa;
  color: #17191c;
  font: 14px Arial, sans-serif;
}}
main {{ max-width: 1100px; margin: 32px auto; padding: 0 20px; }}
header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 22px;
}}
a {{ color: #24292f; }}
section {{
  background: white;
  border: 1px solid #dfe3e8;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
}}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{
  text-align: left;
  padding: 12px;
  border-bottom: 1px solid #e8eaed;
  vertical-align: top;
}}
th {{ font-size: 11px; text-transform: uppercase; color: #69717b; }}
button, .button {{
  border: 0;
  border-radius: 7px;
  background: #22272d;
  color: white;
  padding: 9px 13px;
  text-decoration: none;
  cursor: pointer;
}}
.danger {{ background: #9b1c1c; }}
.muted {{ color: #6c737d; }}
form {{ display: inline; }}
@media (max-width: 700px) {{
  table {{ display: block; overflow: auto; }}
}}
</style>
</head>
<body>
<main>
<header>
  <div>
    <h1>{escaped_title}</h1>
    <p class='muted'>Local operator-controlled storage only.</p>
  </div>
  <a href='/'>Back to assessment</a>
</header>
{body}
</main>
</body>
</html>"""


def _comparison_list(label: str, values: tuple[str, ...]) -> str:
    items = "".join(
        f"<li><code>{html.escape(value)}</code></li>" for value in values
    )
    content = items or "<li>None</li>"
    return (
        f"<section><h2>{html.escape(label)} ({len(values)})</h2>"
        f"<ul>{content}</ul></section>"
    )


@router.post("/history/save")
def save_history(
    url: str | None = Query(default=None, min_length=1, max_length=2048),
    demo: bool = False,
) -> RedirectResponse:
    entry_id = _store().save(_resolve(url, demo))
    return RedirectResponse(f"/history/{entry_id}", status_code=303)


@router.get("/history", response_class=HTMLResponse)
def history_index() -> str:
    entries = _store().list()
    rows = "".join(
        (
            f"<tr><td><a href='/history/{entry.id}'><code>{entry.id}</code></a></td>"
            f"<td>{html.escape(entry.target)}</td>"
            f"<td>{html.escape(entry.generated_at)}</td>"
            f"<td>{html.escape(entry.mode)}</td>"
            f"<td>{entry.total_findings}</td></tr>"
        )
        for entry in entries
    )
    if not rows:
        rows = (
            "<tr><td colspan='5'>"
            "No assessments have been explicitly saved."
            "</td></tr>"
        )
    body = f"""
<section>
<h2>Saved assessments</h2>
<p>Veridra saves nothing here unless the operator explicitly uses the save action.</p>
<table>
<thead>
<tr><th>ID</th><th>Target</th><th>Generated</th><th>Mode</th><th>Findings</th></tr>
</thead>
<tbody>{rows}</tbody>
</table>
</section>
<section>
<h2>Retention</h2>
<form method='post' action='/history/prune?keep=20'>
<button type='submit'>Keep newest 20</button>
</form>
</section>
"""
    return _page("Assessment history", body)


@router.get("/history/compare", response_class=HTMLResponse)
def compare_history(
    before: str = Query(min_length=24, max_length=24),
    after: str = Query(min_length=24, max_length=24),
) -> str:
    try:
        comparison = _store().compare(before, after)
    except HistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    body = (
        f"<section><p><strong>Before:</strong> "
        f"<code>{comparison.before_id}</code><br>"
        f"<strong>After:</strong> <code>{comparison.after_id}</code>"
        "</p></section>"
        + _comparison_list("Added findings", comparison.added)
        + _comparison_list("Resolved findings", comparison.resolved)
        + _comparison_list("Changed findings", comparison.changed)
        + _comparison_list("Unchanged findings", comparison.unchanged)
    )
    return _page("Assessment comparison", body)


@router.get("/history/{entry_id}", response_class=HTMLResponse)
def history_detail(entry_id: str) -> str:
    try:
        assessment = _store().load(entry_id)
    except HistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    entries = [entry for entry in _store().list() if entry.id != entry_id]
    compare_links = "".join(
        (
            "<li><a href='/history/compare?{query}'>"
            "Compare with {entry_id}</a></li>"
        ).format(
            query=html.escape(
                urlencode({"before": entry.id, "after": entry_id}),
                quote=True,
            ),
            entry_id=entry.id,
        )
        for entry in entries[:10]
    )
    compare_content = compare_links or (
        "<li>Save another assessment to compare changes.</li>"
    )
    target = html.escape(str(assessment.target))
    generated = html.escape(assessment.generated_at.isoformat())
    body = f"""
<section>
<h2>{target}</h2>
<p>
<strong>ID:</strong> <code>{entry_id}</code><br>
<strong>Generated:</strong> {generated}<br>
<strong>Mode:</strong> {assessment.mode}<br>
<strong>Findings:</strong> {assessment.summary['total']}
</p>
<form method='post' action='/history/{entry_id}/delete'>
<button class='danger' type='submit'>Delete saved assessment</button>
</form>
</section>
<section>
<h2>Compare</h2>
<ul>{compare_content}</ul>
</section>
"""
    return _page("Saved assessment", body)


@router.post("/history/{entry_id}/delete")
def delete_history(entry_id: str) -> RedirectResponse:
    try:
        _store().delete(entry_id)
    except HistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse("/history", status_code=303)


@router.post("/history/prune")
def prune_history(
    keep: int = Query(default=20, ge=0, le=1000),
) -> RedirectResponse:
    try:
        _store().prune(keep)
    except HistoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/history", status_code=303)
