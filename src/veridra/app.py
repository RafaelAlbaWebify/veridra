from __future__ import annotations

import html

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .collector import CollectionError
from .core import UnsafeTargetError, demo_assessment
from .service import assess_url

app = FastAPI(title="Veridra", version="0.2.0")


def dashboard() -> str:
    assessment = demo_assessment()
    cards = "".join(
        f"<article><span>{key.title()}</span><strong>{value}</strong></article>"
        for key, value in assessment.summary.items()
    )
    rows = "".join(
        f"<tr><td><span class='pill {item.status}'>{item.status}</span></td><td>{html.escape(item.area)}</td><td><strong>{html.escape(item.title)}</strong></td><td>{html.escape(item.summary)}</td><td>{html.escape(item.recommendation or 'No action required.')}</td></tr>"
        for item in assessment.findings
    )
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Veridra</title><style>
*{{box-sizing:border-box}}body{{margin:0;font:14px Arial,sans-serif;background:#f7f8fa;color:#17191c}}aside{{position:fixed;inset:0 auto 0 0;width:230px;background:#f1f3f6;padding:28px 18px;border-right:1px solid #e0e3e8}}aside h1{{margin:0 0 36px;font-size:24px}}nav a{{display:block;padding:12px;border-radius:8px;color:#333;text-decoration:none;margin:4px 0}}nav a.active{{background:#dde1e6;font-weight:700}}main{{margin-left:230px;padding:42px;max-width:1600px}}header{{display:flex;justify-content:space-between;align-items:start;border-bottom:1px solid #e2e5e9;padding-bottom:24px}}h2{{font-size:28px;margin:0}}.muted{{color:#6c737d}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}}article{{background:white;border:1px solid #dfe3e8;border-radius:8px;padding:18px}}article span{{display:block;color:#6c737d;text-transform:uppercase;font-size:12px}}article strong{{display:block;font-size:28px;margin-top:10px}}section{{background:white;border:1px solid #dfe3e8;border-radius:8px;padding:20px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:13px;border-bottom:1px solid #e8eaed;vertical-align:top}}th{{font-size:11px;text-transform:uppercase;color:#69717b}}.pill{{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid}}.passed{{color:#16794a;background:#f0faf5}}.attention{{color:#946200;background:#fff9e8}}@media(max-width:800px){{aside{{position:static;width:auto}}main{{margin:0;padding:20px}}.cards{{grid-template-columns:repeat(2,1fr)}}table{{display:block;overflow:auto}}}}
</style></head><body><aside><h1>Veridra</h1><nav><a class='active'>Overview</a><a>Website health</a><a>Search visibility</a><a>AI discoverability</a><a>Trust signals</a><a>Security posture</a><a>Reports</a></nav></aside><main><header><div><h2>Website assessment</h2><p class='muted'>Visibility, trust and public security evidence.</p></div><button>Run assessment</button></header><div class='cards'>{cards}</div><section><h3>Evidence-backed findings</h3><table><thead><tr><th>Status</th><th>Area</th><th>Finding</th><th>Observation</th><th>Recommended action</th></tr></thead><tbody>{rows}</tbody></table><p class='muted'>Scope: bounded public checks only. This is not a penetration test.</p></section></main></body></html>"""


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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return dashboard()


def main() -> None:
    import uvicorn

    uvicorn.run("veridra.app:app", host="127.0.0.1", port=8000, reload=False)
