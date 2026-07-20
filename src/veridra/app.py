from __future__ import annotations

import html
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import HTMLResponse

from .collector import CollectionError
from .core import Assessment, Status, UnsafeTargetError, demo_assessment
from .exports import build_evidence_package
from .reports import render_report
from .service import assess_url
from .version import __version__

app = FastAPI(title="Veridra", version=__version__)


def _summary_cards(assessment: Assessment) -> str:
    return "".join(
        f"<article><span>{html.escape(key.title())}</span><strong>{value}</strong></article>"
        for key, value in assessment.summary.items()
    )


def _priority_actions(assessment: Assessment) -> str:
    items = [item for item in assessment.findings if item.status == Status.attention][:5]
    if not items:
        return "<p class='muted'>No attention findings are currently prioritised.</p>"
    return "".join(
        "<li><div><span class='eyebrow'>{area} · {severity}</span><strong>{title}</strong>"
        "<p>{summary}</p></div><p class='recommendation'>{recommendation}</p></li>".format(
            area=html.escape(item.area),
            severity=html.escape(item.severity.title()),
            title=html.escape(item.title),
            summary=html.escape(item.summary),
            recommendation=html.escape(item.recommendation or "Review the supporting evidence."),
        )
        for item in items
    )


def _area_rows(assessment: Assessment) -> str:
    return "".join(
        "<tr><td><strong>{area}</strong></td><td>{passed}</td><td>{attention}</td>"
        "<td>{unavailable}</td><td>{total}</td></tr>".format(
            area=html.escape(area),
            passed=counts["passed"],
            attention=counts["attention"],
            unavailable=counts["unavailable"],
            total=counts["total"],
        )
        for area, counts in assessment.area_summary.items()
    )


def _finding_rows(assessment: Assessment) -> str:
    return "".join(
        f"<tr><td><span class='pill {item.status}'>{html.escape(item.status.value)}</span></td><td>{html.escape(item.area)}</td><td><strong>{html.escape(item.title)}</strong></td><td>{html.escape(item.summary)}</td><td>{html.escape(item.recommendation or 'No action required.')}</td></tr>"
        for item in assessment.findings
    )


def dashboard(
    assessment: Assessment,
    *,
    submitted_url: str = "",
    error: str | None = None,
    demo_mode: bool = False,
) -> str:
    cards = _summary_cards(assessment)
    priorities = _priority_actions(assessment)
    area_rows = _area_rows(assessment)
    rows = _finding_rows(assessment)
    escaped_url = html.escape(submitted_url, quote=True)
    error_panel = (
        f"<div class='error' role='alert'>{html.escape(error)}</div>" if error else ""
    )
    query = urlencode({"demo": "true"}) if demo_mode else urlencode({"url": submitted_url})
    report_link = f"/report?{query}"
    export_link = f"/export?{query}"
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Veridra</title><style>
*{{box-sizing:border-box}}body{{margin:0;font:14px Arial,sans-serif;background:#f7f8fa;color:#17191c}}aside{{position:fixed;inset:0 auto 0 0;width:230px;background:#f1f3f6;padding:28px 18px;border-right:1px solid #e0e3e8}}aside h1{{margin:0 0 36px;font-size:24px}}nav a{{display:block;padding:12px;border-radius:8px;color:#333;text-decoration:none;margin:4px 0}}nav a.active{{background:#dde1e6;font-weight:700}}main{{margin-left:230px;padding:42px;max-width:1600px}}header{{display:flex;justify-content:space-between;gap:24px;align-items:start;border-bottom:1px solid #e2e5e9;padding-bottom:24px}}h2{{font-size:28px;margin:0}}h3{{margin-top:0}}.muted{{color:#6c737d}}form{{display:flex;gap:8px;min-width:min(620px,100%)}}input{{flex:1;min-width:220px;padding:11px;border:1px solid #cfd4da;border-radius:7px}}button,.button{{border:0;border-radius:7px;background:#22272d;color:white;padding:11px 16px;text-decoration:none;cursor:pointer}}.button.secondary{{background:#59616b}}.actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}}article{{background:white;border:1px solid #dfe3e8;border-radius:8px;padding:18px}}article span{{display:block;color:#6c737d;text-transform:uppercase;font-size:12px}}article strong{{display:block;font-size:28px;margin-top:10px}}.overview-grid{{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(320px,.8fr);gap:18px;margin-bottom:18px}}section{{background:white;border:1px solid #dfe3e8;border-radius:8px;padding:20px;margin-bottom:18px}}.priority-list{{list-style:none;margin:0;padding:0}}.priority-list li{{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,.7fr);gap:18px;padding:16px 0;border-bottom:1px solid #e8eaed}}.priority-list li:last-child{{border-bottom:0}}.priority-list strong{{display:block;font-size:15px;margin:4px 0}}.priority-list p{{margin:4px 0;line-height:1.45}}.eyebrow{{font-size:11px;text-transform:uppercase;color:#69717b}}.recommendation{{color:#4f5863}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:13px;border-bottom:1px solid #e8eaed;vertical-align:top}}th{{font-size:11px;text-transform:uppercase;color:#69717b}}.pill{{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid}}.passed{{color:#16794a;background:#f0faf5}}.attention{{color:#946200;background:#fff9e8}}.unavailable{{color:#5f6873;background:#f3f4f6}}.error{{margin-top:18px;padding:13px;border-left:3px solid #b42318;background:#fff1f0;color:#7a271a}}@media(max-width:1100px){{.overview-grid{{grid-template-columns:1fr}}}}@media(max-width:1000px){{header{{display:block}}form{{margin-top:18px}}}}@media(max-width:800px){{aside{{position:static;width:auto}}main{{margin:0;padding:20px}}.cards{{grid-template-columns:repeat(2,1fr)}}table{{display:block;overflow:auto}}form{{display:block}}input{{width:100%;margin-bottom:8px}}.priority-list li{{grid-template-columns:1fr}}}}
</style></head><body><aside><h1>Veridra</h1><nav><a class='active'>Overview</a><a>Website health</a><a>Search visibility</a><a>AI discoverability</a><a>Trust signals</a><a>Security posture</a><a href='{html.escape(report_link, quote=True)}'>Reports</a></nav></aside><main><header><div><h2>Website assessment</h2><p class='muted'>Visibility, trust and public security evidence.</p></div><div><form method='get' action='/'><label class='muted' for='url'>Public website</label><input id='url' name='url' type='text' maxlength='2048' placeholder='example.com' value='{escaped_url}' required><div class='actions'><button type='submit'>Run assessment</button><a class='button' href='{html.escape(report_link, quote=True)}'>Open report</a><a class='button secondary' href='{html.escape(export_link, quote=True)}'>Export evidence</a></div></form></div></header>{error_panel}<div class='cards'>{cards}</div><div class='overview-grid'><section aria-labelledby='priority-heading'><h3 id='priority-heading'>Priority actions</h3><p class='muted'>The first five attention findings in deterministic severity order.</p><ol class='priority-list'>{priorities}</ol></section><section aria-labelledby='areas-heading'><h3 id='areas-heading'>Assessment areas</h3><table><thead><tr><th>Area</th><th>Passed</th><th>Attention</th><th>Unavailable</th><th>Total</th></tr></thead><tbody>{area_rows}</tbody></table></section></div><section><h3>Evidence-backed findings</h3><table><thead><tr><th>Status</th><th>Area</th><th>Finding</th><th>Observation</th><th>Recommended action</th></tr></thead><tbody>{rows}</tbody></table><p class='muted'>Scope: bounded public checks only. This is not a penetration test.</p></section></main></body></html>"""


def _resolve_assessment(url: str | None, demo: bool) -> Assessment:
    if demo:
        return demo_assessment()
    if url is None:
        raise HTTPException(status_code=400, detail="A target URL is required.")
    try:
        return assess_url(url)
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/demo")
def demo() -> dict[str, object]:
    return demo_assessment().model_dump(mode="json")


@app.get("/api/assess")
def assess(url: str = Query(min_length=1, max_length=2048)) -> dict[str, object]:
    try:
        return assess_url(url).model_dump(mode="json")
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/report", response_class=HTMLResponse)
def report(
    url: str | None = Query(default=None, min_length=1, max_length=2048),
    demo: bool = False,
) -> str:
    return render_report(_resolve_assessment(url, demo))


@app.get("/export")
def export(
    url: str | None = Query(default=None, min_length=1, max_length=2048),
    demo: bool = False,
) -> Response:
    package = build_evidence_package(_resolve_assessment(url, demo))
    return Response(
        content=package.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(
    url: str | None = Query(default=None, min_length=1, max_length=2048),
) -> str:
    if url is None:
        return dashboard(demo_assessment(), demo_mode=True)
    try:
        assessment = assess_url(url)
        return dashboard(assessment, submitted_url=url)
    except (UnsafeTargetError, CollectionError) as exc:
        return dashboard(
            demo_assessment(),
            submitted_url=url,
            error=str(exc),
            demo_mode=True,
        )


def main() -> None:
    import uvicorn

    uvicorn.run("veridra.app:app", host="127.0.0.1", port=8000, reload=False)
