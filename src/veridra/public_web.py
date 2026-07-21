from __future__ import annotations

import html
from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from .collector import CollectionError
from .core import Assessment, Finding, Status, UnsafeTargetError
from .service import assess_url

router = APIRouter(prefix="/free", tags=["free-tools"])


@dataclass(frozen=True)
class ToolDefinition:
    slug: str
    title: str
    description: str
    areas: tuple[str, ...]
    limitation: str


TOOLS = (
    ToolDefinition(
        slug="website-audit",
        title="Website Audit",
        description="Check technical health, search readiness, trust and passive public security signals.",
        areas=(),
        limitation="Bounded public checks only. This is not a penetration test or full SEO crawl.",
    ),
    ToolDefinition(
        slug="ai-readiness",
        title="AI Readiness",
        description="Check crawler access, structured discoverability and public content signals used by AI systems.",
        areas=("AI discoverability",),
        limitation="This measures deterministic readiness, not whether an AI system mentions or recommends the business.",
    ),
    ToolDefinition(
        slug="trust-signals",
        title="Trust Signals",
        description="Review visible business, legal, language, social and contact-page signals.",
        areas=("Trust signals",),
        limitation="Linked pages are detected heuristically and are not treated as proof of business legitimacy.",
    ),
    ToolDefinition(
        slug="security-posture",
        title="Security Posture",
        description="Review passive HTTPS, header, DNS and email-domain posture evidence.",
        areas=("Security posture",),
        limitation="Passive public posture only. No ports, credentials, exploits or active vulnerability testing.",
    ),
    ToolDefinition(
        slug="local-presence",
        title="Local Presence Readiness",
        description="Check website signals that support a consistent local-business presence.",
        areas=("Search visibility", "Trust signals"),
        limitation="Google Business Profile, Maps rankings, reviews and citations are not queried in this version.",
    ),
)
_TOOL_BY_SLUG = {item.slug: item for item in TOOLS}


def _shell(body: str, *, title: str) -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>
*{{box-sizing:border-box}}html,body{{max-width:100%;overflow-x:hidden}}body{{margin:0;background:#f6f7f9;color:#17202a;font:15px Arial,sans-serif}}a{{color:inherit}}header{{background:#fff;border-bottom:1px solid #e1e5ea}}.nav{{max-width:1180px;margin:auto;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;gap:18px}}.brand{{font-size:23px;font-weight:800;text-decoration:none}}.operator{{font-size:13px;color:#59636f}}main{{max-width:1180px;margin:auto;padding:56px 24px 72px}}.hero{{text-align:center;max-width:820px;margin:0 auto 44px}}.hero h1{{font-size:44px;line-height:1.08;margin:0 0 18px}}.hero p{{font-size:18px;line-height:1.6;color:#5f6975}}form.scan{{display:flex;max-width:760px;margin:28px auto 0;padding:8px;background:#fff;border:1px solid #d9dee5;border-radius:12px;box-shadow:0 8px 30px rgba(26,35,45,.07)}}input{{flex:1;min-width:0;border:0;padding:14px;font-size:16px;outline:none}}button,.button{{border:0;border-radius:8px;background:#1f2933;color:#fff;padding:13px 18px;font-weight:700;text-decoration:none;cursor:pointer}}.secondary{{background:#66717d}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}}.card,.panel{{background:#fff;border:1px solid #dfe4ea;border-radius:12px;padding:24px}}.card h2{{margin:0 0 10px;font-size:19px}}.card p{{color:#606b77;line-height:1.55;min-height:72px}}.card a{{font-weight:700;text-decoration:none}}.eyebrow{{text-transform:uppercase;letter-spacing:.08em;font-size:11px;color:#66717d;font-weight:700}}.scope{{margin-top:32px;background:#eef2f6;border-radius:10px;padding:18px;color:#4d5965}}.result-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap;margin-bottom:22px}}.result-head h1{{margin:5px 0 8px}}.summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:18px 0}}.metric{{background:#fff;border:1px solid #dfe4ea;border-radius:10px;padding:18px}}.metric span{{display:block;color:#68737f;text-transform:uppercase;font-size:11px}}.metric strong{{display:block;font-size:28px;margin-top:8px}}table{{width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{text-align:left;padding:13px;border-bottom:1px solid #e5e8ec;vertical-align:top;overflow-wrap:anywhere}}th{{font-size:11px;text-transform:uppercase;color:#69747f}}.pill{{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid}}.passed{{color:#14764a;background:#eff9f4}}.attention{{color:#8a5c00;background:#fff8e5}}.unavailable{{color:#59636e;background:#f1f3f5}}.notice{{padding:16px;border-left:3px solid #8a5c00;background:#fff8e5;margin:18px 0}}.error{{padding:16px;border-left:3px solid #b42318;background:#fff0ee;color:#7a271a}}@media(max-width:900px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.summary{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:620px){{main{{padding:36px 16px 56px}}.hero h1{{font-size:34px}}form.scan{{display:block}}input,button{{width:100%}}.grid{{grid-template-columns:1fr}}.summary{{grid-template-columns:1fr 1fr}}table{{display:block;overflow:auto}}}}
</style></head><body><header><div class='nav'><a class='brand' href='/free'>Veridra</a><span class='operator'>Free tools · no registration</span></div></header><main>{body}</main></body></html>"""


def _tool_cards() -> str:
    return "".join(
        "<article class='card'><span class='eyebrow'>Free tool</span><h2>{title}</h2><p>{description}</p><a href='/free/{slug}'>Open tool →</a></article>".format(
            title=html.escape(item.title),
            description=html.escape(item.description),
            slug=item.slug,
        )
        for item in TOOLS
    )


def _scan_form(tool: ToolDefinition | None = None, value: str = "") -> str:
    action = f"/free/{tool.slug}" if tool else "/free/website-audit"
    return "<form class='scan' method='get' action='{action}'><label for='free-url' style='position:absolute;left:-9999px'>Public website</label><input id='free-url' name='url' maxlength='2048' required placeholder='Enter your website, for example example.com' value='{value}'><button type='submit'>Analyse website</button></form>".format(
        action=action,
        value=html.escape(value, quote=True),
    )


def _selected_findings(assessment: Assessment, tool: ToolDefinition) -> list[Finding]:
    if not tool.areas:
        return assessment.findings
    return [item for item in assessment.findings if item.area in tool.areas]


def _summary(findings: list[Finding]) -> dict[str, int]:
    return {
        "passed": sum(item.status == Status.passed for item in findings),
        "attention": sum(item.status == Status.attention for item in findings),
        "unavailable": sum(item.status == Status.unavailable for item in findings),
        "total": len(findings),
    }


def _finding_rows(findings: list[Finding]) -> str:
    if not findings:
        return "<tr><td colspan='4'>No findings are available for this tool.</td></tr>"
    return "".join(
        "<tr><td><span class='pill {status}'>{status}</span></td><td>{area}</td><td><strong>{title}</strong><br>{summary}</td><td>{recommendation}</td></tr>".format(
            status=html.escape(item.status.value),
            area=html.escape(item.area),
            title=html.escape(item.title),
            summary=html.escape(item.summary),
            recommendation=html.escape(item.recommendation or "No action required."),
        )
        for item in findings
    )


@router.get("", response_class=HTMLResponse)
def free_home() -> str:
    body = "<section class='hero'><span class='eyebrow'>Website and local-business visibility</span><h1>Understand what is helping—or hurting—your online presence</h1><p>Run useful website, AI-readiness, trust and passive-security checks without creating an account.</p>{form}</section><section class='grid'>{cards}</section><div class='scope'><strong>Free-tier scope:</strong> bounded public checks, no registration and no anonymous result storage. Veridra does not log in, submit forms or perform penetration testing.</div>".format(
        form=_scan_form(),
        cards=_tool_cards(),
    )
    return _shell(body, title="Veridra free website tools")


@router.get("/{slug}", response_class=HTMLResponse)
def free_tool(
    slug: str,
    url: str | None = Query(default=None, min_length=1, max_length=2048),
) -> str:
    tool = _TOOL_BY_SLUG.get(slug)
    if tool is None:
        raise HTTPException(status_code=404, detail="Unknown free tool.")
    if url is None:
        body = "<section class='hero'><span class='eyebrow'>Free tool</span><h1>{title}</h1><p>{description}</p>{form}</section><div class='scope'>{limitation}</div>".format(
            title=html.escape(tool.title),
            description=html.escape(tool.description),
            form=_scan_form(tool),
            limitation=html.escape(tool.limitation),
        )
        return _shell(body, title=f"{tool.title} — Veridra")
    try:
        assessment = assess_url(url)
    except (UnsafeTargetError, CollectionError) as exc:
        body = "<section class='hero'><span class='eyebrow'>Free tool</span><h1>{title}</h1>{form}</section><div class='error' role='alert'>{error}</div>".format(
            title=html.escape(tool.title),
            form=_scan_form(tool, url),
            error=html.escape(str(exc)),
        )
        return _shell(body, title=f"{tool.title} — Veridra")
    findings = _selected_findings(assessment, tool)
    counts = _summary(findings)
    query = urlencode({"url": url})
    metrics = "".join(
        f"<article class='metric'><span>{html.escape(label.title())}</span><strong>{value}</strong></article>"
        for label, value in counts.items()
    )
    body = "<div class='result-head'><div><span class='eyebrow'>Free result</span><h1>{title}</h1><p>{target}</p></div><a class='button secondary' href='/free/{slug}'>Check another website</a></div><section class='summary'>{metrics}</section><div class='notice'><strong>Scope:</strong> {limitation}</div><section class='panel'><h2>Findings</h2><table><thead><tr><th>Status</th><th>Area</th><th>Finding</th><th>Recommended action</th></tr></thead><tbody>{rows}</tbody></table></section><p><a href='/free/{slug}?{query}'>Share this query-state result</a></p>".format(
        title=html.escape(tool.title),
        target=html.escape(str(assessment.target)),
        slug=tool.slug,
        metrics=metrics,
        limitation=html.escape(tool.limitation),
        rows=_finding_rows(findings),
        query=html.escape(query, quote=True),
    )
    return _shell(body, title=f"{tool.title} result — Veridra")
