from __future__ import annotations

import html
import json

from .core import Assessment, Finding, Status
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile

_SCOPE = (
    "Scope: bounded public checks only. This is not a penetration test and "
    "does not inspect authenticated functionality, source code, server "
    "configuration, or private infrastructure."
)


def _finding_row(item: Finding, *, show_raw_evidence: bool) -> str:
    evidence_cell = ""
    if show_raw_evidence:
        evidence_json = json.dumps(
            item.evidence,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        evidence_cell = f"<td><pre>{html.escape(evidence_json)}</pre></td>"
    return (
        f"<tr><td>{html.escape(item.status.value)}</td>"
        f"<td>{html.escape(item.area)}</td>"
        f"<td>{html.escape(item.title)}</td>"
        f"<td>{html.escape(item.summary)}</td>"
        f"<td>{html.escape(item.recommendation or 'No action required.')}</td>"
        f"{evidence_cell}</tr>"
    )


def _priority_item(item: Finding) -> str:
    recommendation = html.escape(
        item.recommendation or "Review the supporting evidence."
    )
    return (
        "<li>"
        f"<div><span>{html.escape(item.area)} · {html.escape(item.severity.title())}</span>"
        f"<strong>{html.escape(item.title)}</strong>"
        f"<p>{html.escape(item.summary)}</p></div>"
        f"<p class='recommendation'>{recommendation}</p>"
        "</li>"
    )


def _area_row(area: str, values: dict[str, int]) -> str:
    return (
        f"<tr><td>{html.escape(area)}</td>"
        f"<td>{values['passed']}</td>"
        f"<td>{values['attention']}</td>"
        f"<td>{values['unavailable']}</td>"
        f"<td>{values['total']}</td></tr>"
    )


def _profile_header(profile: ReportProfile) -> str:
    client = (
        f"<p><strong>Prepared for:</strong> {html.escape(profile.client_name)}</p>"
        if profile.client_name
        else ""
    )
    consultant = (
        f"<p><strong>Consultant:</strong> {html.escape(profile.consultant_name)}</p>"
        if profile.consultant_name
        else ""
    )
    introduction = (
        f"<section class='introduction'><h2>Introduction</h2><p>{html.escape(profile.introduction)}</p></section>"
        if profile.introduction
        else ""
    )
    return client + consultant + introduction


def _profile_cta(profile: ReportProfile) -> str:
    if not profile.call_to_action_label or not profile.call_to_action_url:
        return ""
    return (
        "<section class='cta'><h2>Next step</h2>"
        f"<a href='{html.escape(profile.call_to_action_url, quote=True)}'>"
        f"{html.escape(profile.call_to_action_label)}</a></section>"
    )


def render_report(
    assessment: Assessment,
    profile: ReportProfile | None = None,
) -> str:
    active_profile = profile or DEFAULT_REPORT_PROFILE
    target = html.escape(str(assessment.target))
    summary_cards = "".join(
        f"<article><span>{html.escape(key.title())}</span><strong>{value}</strong></article>"
        for key, value in assessment.summary.items()
    )
    priority_findings = [
        item for item in assessment.findings if item.status == Status.attention
    ][:5]
    priority_items = "".join(_priority_item(item) for item in priority_findings)
    if not priority_items:
        priority_items = "<p class='muted'>No attention findings are currently prioritised.</p>"
    area_rows = "".join(
        _area_row(area, values)
        for area, values in assessment.area_summary.items()
    )
    rows = "".join(
        _finding_row(item, show_raw_evidence=active_profile.show_raw_evidence)
        for item in assessment.findings
    )
    evidence_heading = "<th>Evidence</th>" if active_profile.show_raw_evidence else ""
    profile_header = _profile_header(active_profile)
    profile_cta = _profile_cta(active_profile)
    organisation = html.escape(active_profile.organisation_name)
    scope = html.escape(_SCOPE)
    generated = html.escape(assessment.generated_at.isoformat())
    mode = html.escape(assessment.mode.title())
    accent = html.escape(active_profile.accent_colour, quote=True)
    language = html.escape(active_profile.language, quote=True)
    return f"""<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{organisation} assessment report</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #eef1f4; color: #17191c; font: 14px Arial, sans-serif; }}
main {{ max-width: 1300px; margin: 32px auto; background: white; padding: 40px; border: 1px solid #dfe3e8; }}
header {{ display: flex; justify-content: space-between; gap: 24px; border-bottom: 4px solid {accent}; padding-bottom: 22px; }}
h1 {{ margin: 0 0 8px; font-size: 30px; }}
.target {{ word-break: break-all; color: #555; }}
.meta {{ margin: 14px 0 0; display: flex; flex-wrap: wrap; gap: 18px; color: #555; }}
.cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 24px 0; }}
article {{ border: 1px solid #dfe3e8; padding: 16px; }}
article span {{ display: block; text-transform: uppercase; font-size: 11px; color: #68707a; }}
article strong {{ display: block; font-size: 26px; margin-top: 8px; }}
.priority-list {{ list-style: none; margin: 0 0 28px; padding: 0; border: 1px solid #dfe3e8; }}
.priority-list li {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, .7fr); gap: 24px; padding: 16px; border-bottom: 1px solid #e5e7ea; }}
.priority-list li:last-child {{ border-bottom: 0; }}
.priority-list span {{ display: block; color: #68707a; font-size: 11px; text-transform: uppercase; }}
.priority-list strong {{ display: block; margin: 5px 0; }}
.priority-list p {{ margin: 4px 0; line-height: 1.45; }}
.recommendation, .muted {{ color: #68707a; }}
.introduction, .cta {{ margin: 24px 0; padding: 18px; border-left: 4px solid {accent}; background: #f7f8fa; }}
.cta a, button {{ display: inline-block; border: 0; border-radius: 6px; background: {accent}; color: white; padding: 10px 14px; text-decoration: none; cursor: pointer; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 28px; }}
th, td {{ text-align: left; vertical-align: top; padding: 10px; border-bottom: 1px solid #e5e7ea; }}
th {{ font-size: 11px; text-transform: uppercase; color: #68707a; }}
pre {{ white-space: pre-wrap; word-break: break-word; font-size: 11px; margin: 0; }}
.scope {{ margin-top: 26px; padding: 14px; background: #f6f7f9; border-left: 3px solid #707780; }}
@media (max-width: 800px) {{ main {{ margin: 0; padding: 20px; }} .cards {{ grid-template-columns: repeat(2, 1fr); }} .priority-list li {{ grid-template-columns: 1fr; }} table {{ display: block; overflow: auto; }} }}
@media print {{ body {{ background: white; }} main {{ border: 0; margin: 0; max-width: none; padding: 0; }} button {{ display: none; }} }}
</style>
</head>
<body><main>
<header><div><h1>{organisation} assessment report</h1><div class="target">{target}</div>
<div class="meta"><span><strong>Mode:</strong> {mode}</span><span><strong>Generated:</strong> {generated}</span><span><strong>Elapsed:</strong> {assessment.elapsed_ms} ms</span><span><strong>Schema:</strong> {html.escape(assessment.schema_version)}</span></div>
{profile_header}</div><button onclick="window.print()">Print report</button></header>
<div class="cards">{summary_cards}</div>
<h2>Priority actions</h2><p class="muted">The first five attention findings in deterministic severity order.</p><ol class="priority-list">{priority_items}</ol>
<h2>Assessment areas</h2><table><thead><tr><th>Area</th><th>Passed</th><th>Attention</th><th>Unavailable</th><th>Total</th></tr></thead><tbody>{area_rows}</tbody></table>
<h2>Evidence-backed findings</h2><table><thead><tr><th>Status</th><th>Area</th><th>Finding</th><th>Observation</th><th>Recommended action</th>{evidence_heading}</tr></thead><tbody>{rows}</tbody></table>
{profile_cta}<p class="scope">{scope}</p>
</main></body></html>"""
