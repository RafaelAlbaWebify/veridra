from __future__ import annotations

import html
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import HTMLResponse

from .collector import CollectionError
from .core import Assessment, Finding, Status, UnsafeTargetError, demo_assessment
from .exports import build_evidence_package
from .history_web import router as history_router
from .profile_store import ProfileStore, ProfileStoreError
from .profile_web import router as profile_router
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile
from .reports import render_report
from .service import assess_url
from .version import __version__

app = FastAPI(title="Veridra", version=__version__)
app.include_router(history_router)
app.include_router(profile_router)

_AREAS = (
    "Website health",
    "Search visibility",
    "AI discoverability",
    "Trust signals",
    "Security posture",
)
_STATUSES = ("passed", "attention", "unavailable")


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
            recommendation=html.escape(
                item.recommendation or "Review the supporting evidence."
            ),
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


def _filtered_findings(
    assessment: Assessment,
    area: str | None,
    status: str | None,
) -> list[Finding]:
    if area is not None and area not in _AREAS:
        raise HTTPException(status_code=400, detail="Unknown assessment area.")
    if status is not None and status not in _STATUSES:
        raise HTTPException(status_code=400, detail="Unknown finding status.")
    return [
        item
        for item in assessment.findings
        if (area is None or item.area == area)
        and (status is None or item.status.value == status)
    ]


def _finding_rows(findings: list[Finding]) -> str:
    if not findings:
        return (
            "<tr><td colspan='5' class='empty'>"
            "No findings match the selected filters.</td></tr>"
        )
    return "".join(
        "<tr><td><span class='pill {status}'>{status}</span></td>"
        "<td>{area}</td><td><strong>{title}</strong></td>"
        "<td>{summary}</td><td>{recommendation}</td></tr>".format(
            status=html.escape(item.status.value),
            area=html.escape(item.area),
            title=html.escape(item.title),
            summary=html.escape(item.summary),
            recommendation=html.escape(item.recommendation or "No action required."),
        )
        for item in findings
    )


def _query_base(submitted_url: str, demo_mode: bool) -> dict[str, str]:
    return {"demo": "true"} if demo_mode else {"url": submitted_url}


def _nav_links(base: dict[str, str], selected_area: str | None) -> str:
    links = [("Overview", None), *((area, area) for area in _AREAS)]
    return "".join(
        "<a class='{active}' href='/?{query}'>{label}</a>".format(
            active="active" if area == selected_area else "",
            query=html.escape(
                urlencode({**base, **({"area": area} if area else {})}),
                quote=True,
            ),
            label=html.escape(label),
        )
        for label, area in links
    )


def dashboard(
    assessment: Assessment,
    *,
    submitted_url: str = "",
    error: str | None = None,
    demo_mode: bool = False,
    area: str | None = None,
    status: str | None = None,
) -> str:
    findings = _filtered_findings(assessment, area, status)
    escaped_url = html.escape(submitted_url, quote=True)
    error_panel = (
        f"<div class='error' role='alert'>{html.escape(error)}</div>" if error else ""
    )
    base = _query_base(submitted_url, demo_mode)
    report_link = f"/report?{urlencode(base)}"
    export_link = f"/export?{urlencode(base)}"
    save_link = f"/history/save?{urlencode(base)}"
    area_options = "<option value=''>All areas</option>" + "".join(
        f"<option value='{html.escape(value, quote=True)}'"
        f"{' selected' if value == area else ''}>{html.escape(value)}</option>"
        for value in _AREAS
    )
    status_options = "<option value=''>All statuses</option>" + "".join(
        f"<option value='{value}'{' selected' if value == status else ''}>"
        f"{value.title()}</option>"
        for value in _STATUSES
    )
    hidden_target = (
        "<input type='hidden' name='demo' value='true'>"
        if demo_mode
        else f"<input type='hidden' name='url' value='{escaped_url}'>"
    )
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Veridra</title><style>
*{{box-sizing:border-box}}html,body{{max-width:100%;overflow-x:hidden}}body{{margin:0;font:14px Arial,sans-serif;background:#f7f8fa;color:#17191c}}aside{{position:fixed;inset:0 auto 0 0;width:230px;background:#f1f3f6;padding:28px 18px;border-right:1px solid #e0e3e8}}aside h1{{margin:0 0 36px;font-size:24px}}nav a{{display:block;padding:12px;border-radius:8px;color:#333;text-decoration:none;margin:4px 0}}nav a.active{{background:#dde1e6;font-weight:700}}main{{margin-left:230px;padding:42px;max-width:1600px;min-width:0}}header{{display:flex;justify-content:space-between;gap:24px;align-items:start;border-bottom:1px solid #e2e5e9;padding-bottom:24px}}h2{{font-size:28px;margin:0}}h3{{margin-top:0}}.muted{{color:#6c737d}}form{{display:flex;gap:8px;min-width:min(620px,100%);max-width:100%}}input,select{{flex:1;min-width:160px;max-width:100%;padding:11px;border:1px solid #cfd4da;border-radius:7px;background:white}}button,.button{{border:0;border-radius:7px;background:#22272d;color:white;padding:11px 16px;text-decoration:none;cursor:pointer}}.button.secondary{{background:#59616b}}.actions,.filters{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:24px 0}}article,section{{background:white;border:1px solid #dfe3e8;border-radius:8px;padding:20px;min-width:0}}article span{{display:block;color:#6c737d;text-transform:uppercase;font-size:12px}}article strong{{display:block;font-size:28px;margin-top:10px}}.overview-grid{{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,.8fr);gap:18px;margin-bottom:18px}}section{{margin-bottom:18px}}.priority-list{{list-style:none;margin:0;padding:0}}.priority-list li{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.7fr);gap:18px;padding:16px 0;border-bottom:1px solid #e8eaed}}.eyebrow{{font-size:11px;text-transform:uppercase;color:#69717b}}table{{width:100%;max-width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{text-align:left;padding:13px;border-bottom:1px solid #e8eaed;vertical-align:top;overflow-wrap:anywhere}}th{{font-size:11px;text-transform:uppercase;color:#69717b}}.pill{{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid}}.passed{{color:#16794a;background:#f0faf5}}.attention{{color:#946200;background:#fff9e8}}.unavailable{{color:#5f6873;background:#f3f4f6}}.error{{margin-top:18px;padding:13px;border-left:3px solid #b42318;background:#fff1f0;color:#7a271a}}.finding-head{{display:flex;justify-content:space-between;gap:16px;align-items:end;flex-wrap:wrap}}.empty{{text-align:center;color:#69717b;padding:28px}}@media(max-width:1100px){{.overview-grid{{grid-template-columns:1fr}}}}@media(max-width:1000px){{header{{display:block}}form{{margin-top:18px}}}}@media(max-width:800px){{aside{{position:static;width:auto}}main{{margin:0;padding:20px}}.cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}table{{display:block;overflow:auto}}form{{display:block;min-width:0}}input,select{{width:100%;min-width:0;margin-bottom:8px}}.priority-list li{{grid-template-columns:1fr}}}}
</style></head><body><aside><h1>Veridra</h1><nav>{_nav_links(base, area)}<a href='{html.escape(report_link, quote=True)}'>Reports</a><a href='/profiles'>Report profiles</a><a href='/history'>History</a></nav></aside><main><header><div><h2>Website assessment</h2><p class='muted'>Visibility, trust and public security evidence.</p></div><div><form method='get' action='/'><label class='muted' for='url'>Public website</label><input id='url' name='url' type='text' maxlength='2048' placeholder='example.com' value='{escaped_url}' required><div class='actions'><button type='submit'>Run assessment</button><a class='button' href='{html.escape(report_link, quote=True)}'>Open report</a><a class='button secondary' href='{html.escape(export_link, quote=True)}'>Export evidence</a><button type='submit' formmethod='post' formaction='{html.escape(save_link, quote=True)}'>Save locally</button></div></form></div></header>{error_panel}<div class='cards'>{_summary_cards(assessment)}</div><div class='overview-grid'><section aria-labelledby='priority-heading'><h3 id='priority-heading'>Priority actions</h3><p class='muted'>The first five attention findings in deterministic severity order.</p><ol class='priority-list'>{_priority_actions(assessment)}</ol></section><section aria-labelledby='areas-heading'><h3 id='areas-heading'>Assessment areas</h3><table><thead><tr><th>Area</th><th>Passed</th><th>Attention</th><th>Unavailable</th><th>Total</th></tr></thead><tbody>{_area_rows(assessment)}</tbody></table></section></div><section><div class='finding-head'><div><h3>Evidence-backed findings</h3><p class='muted'>{len(findings)} of {len(assessment.findings)} findings displayed.</p></div><form class='filters' method='get' action='/'>{hidden_target}<label for='area'>Area</label><select id='area' name='area'>{area_options}</select><label for='status'>Status</label><select id='status' name='status'>{status_options}</select><button type='submit'>Apply filters</button></form></div><table><thead><tr><th>Status</th><th>Area</th><th>Finding</th><th>Observation</th><th>Recommended action</th></tr></thead><tbody>{_finding_rows(findings)}</tbody></table><p class='muted'>Scope: bounded public checks only. This is not a penetration test.</p></section></main></body></html>"""


def _resolve_assessment(url: str | None, demo: bool) -> Assessment:
    if demo:
        return demo_assessment()
    if url is None:
        raise HTTPException(status_code=400, detail="A target URL is required.")
    try:
        return assess_url(url)
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_profile(profile: str | None) -> ReportProfile:
    if profile is None:
        return DEFAULT_REPORT_PROFILE
    try:
        return ProfileStore().load(profile)
    except ProfileStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    profile: str | None = Query(default=None, max_length=24),
) -> str:
    return render_report(_resolve_assessment(url, demo), _resolve_profile(profile))


@app.get("/export")
def export(
    url: str | None = Query(default=None, min_length=1, max_length=2048),
    demo: bool = False,
    profile: str | None = Query(default=None, max_length=24),
) -> Response:
    package = build_evidence_package(
        _resolve_assessment(url, demo),
        _resolve_profile(profile),
    )
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
    demo: bool = False,
    area: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
) -> str:
    if demo or url is None:
        return dashboard(demo_assessment(), demo_mode=True, area=area, status=status)
    try:
        return dashboard(assess_url(url), submitted_url=url, area=area, status=status)
    except (UnsafeTargetError, CollectionError) as exc:
        return dashboard(
            demo_assessment(),
            submitted_url=url,
            error=str(exc),
            demo_mode=True,
            area=area,
            status=status,
        )


def main() -> None:
    import uvicorn

    uvicorn.run("veridra.app:app", host="127.0.0.1", port=8000, reload=False)
