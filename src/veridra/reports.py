from __future__ import annotations

import html
import json
from collections import Counter, defaultdict

from .core import Assessment, Finding, Status
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile

_SCOPE = (
    "Scope: bounded public checks only. This is not a penetration test and "
    "does not inspect authenticated functionality, source code, server "
    "configuration, or private infrastructure."
)
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


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


def _area_summary(findings: list[Finding]) -> dict[str, dict[str, int]]:
    values: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for item in findings:
        values[item.area][item.status.value] += 1
        values[item.area]["total"] += 1
    return {
        area: {
            "passed": counts.get("passed", 0),
            "attention": counts.get("attention", 0),
            "unavailable": counts.get("unavailable", 0),
            "total": counts.get("total", 0),
        }
        for area, counts in sorted(values.items())
    }


def _summary(findings: list[Finding]) -> dict[str, int]:
    counts = Counter(item.status.value for item in findings)
    return {
        "passed": counts.get("passed", 0),
        "attention": counts.get("attention", 0),
        "unavailable": counts.get("unavailable", 0),
        "total": len(findings),
    }


def _area_row(area: str, values: dict[str, int]) -> str:
    return (
        f"<tr><td>{html.escape(area)}</td>"
        f"<td>{values['passed']}</td>"
        f"<td>{values['attention']}</td>"
        f"<td>{values['unavailable']}</td>"
        f"<td>{values['total']}</td></tr>"
    )


def _contact(profile: ReportProfile) -> str:
    values = [
        profile.consultant_name,
        profile.agency_email,
        profile.agency_phone,
        profile.agency_website,
    ]
    visible = [html.escape(value) for value in values if value]
    return " · ".join(visible)


def _executive_summary(profile: ReportProfile, findings: list[Finding]) -> str:
    attention = [item for item in findings if item.status == Status.attention]
    high = sum(item.severity.lower() in {"critical", "high"} for item in attention)
    areas = len({item.area for item in attention})
    generated = (
        f"This assessment identified {len(attention)} attention findings across "
        f"{areas} areas, including {high} high-priority observations. "
        "Priorities are derived from finding status and severity; no synthetic score is used."
    )
    text = profile.executive_summary or generated
    return (
        "<section class='executive'><h2>Executive summary</h2>"
        f"<p>{html.escape(text)}</p></section>"
    )


def _priority_actions(findings: list[Finding]) -> str:
    attention = sorted(
        (item for item in findings if item.status == Status.attention),
        key=lambda item: (
            _SEVERITY_ORDER.get(item.severity.lower(), 5),
            item.area.lower(),
            item.title.lower(),
        ),
    )[:10]
    content = "".join(_priority_item(item) for item in attention)
    if not content:
        content = "<p class='muted'>No attention findings are currently prioritised.</p>"
    return (
        "<section><h2>Priority actions</h2>"
        "<p class='muted'>Attention findings ordered by explicit severity and area.</p>"
        f"<ol class='priority-list'>{content}</ol></section>"
    )


def _business_impact(findings: list[Finding]) -> str:
    attention = [item for item in findings if item.status == Status.attention]
    grouped: defaultdict[str, list[Finding]] = defaultdict(list)
    for item in attention:
        grouped[item.area].append(item)
    rows = "".join(
        "<tr><td>{area}</td><td>{count}</td><td>{high}</td><td>{summary}</td></tr>".format(
            area=html.escape(area),
            count=len(items),
            high=sum(
                item.severity.lower() in {"critical", "high"} for item in items
            ),
            summary=html.escape(items[0].summary),
        )
        for area, items in sorted(grouped.items())
    )
    if not rows:
        rows = "<tr><td colspan='4'>No attention findings are available.</td></tr>"
    return (
        "<section><h2>Business-impact view</h2>"
        "<p class='muted'>A transparent grouping of observed findings, not a financial-impact estimate.</p>"
        "<table><thead><tr><th>Area</th><th>Attention</th><th>High priority</th>"
        f"<th>Example observation</th></tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _roadmap(findings: list[Finding]) -> str:
    groups = (
        ("Immediate review", {"critical", "high"}),
        ("Planned improvement", {"medium"}),
        ("Monitor or refine", {"low", "info"}),
    )
    columns = []
    attention = [item for item in findings if item.status == Status.attention]
    for heading, severities in groups:
        items = [item for item in attention if item.severity.lower() in severities][:8]
        entries = "".join(
            f"<li><strong>{html.escape(item.title)}</strong><br>"
            f"{html.escape(item.recommendation or item.summary)}</li>"
            for item in items
        ) or "<li>No matching attention findings.</li>"
        columns.append(f"<article><h3>{heading}</h3><ul>{entries}</ul></article>")
    return (
        "<section><h2>Implementation roadmap</h2>"
        "<p class='muted'>Suggested sequencing derived from explicit finding severity; owners and deadlines remain operator decisions.</p>"
        f"<div class='roadmap'>{''.join(columns)}</div></section>"
    )


def _assessment_areas(findings: list[Finding]) -> str:
    rows = "".join(
        _area_row(area, values) for area, values in _area_summary(findings).items()
    )
    return (
        "<section><h2>Assessment areas</h2><table><thead><tr><th>Area</th>"
        "<th>Passed</th><th>Attention</th><th>Unavailable</th><th>Total</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _findings(findings: list[Finding], profile: ReportProfile) -> str:
    rows = "".join(
        _finding_row(item, show_raw_evidence=profile.show_raw_evidence)
        for item in findings
    ) or "<tr><td colspan='6'>No findings are included in this template.</td></tr>"
    evidence_heading = "<th>Evidence</th>" if profile.show_raw_evidence else ""
    return (
        "<section><h2>Evidence-backed findings</h2><table><thead><tr>"
        "<th>Status</th><th>Area</th><th>Finding</th><th>Observation</th>"
        f"<th>Recommended action</th>{evidence_heading}</tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def _conclusion(profile: ReportProfile) -> str:
    if not profile.conclusion:
        return ""
    return (
        "<section class='conclusion'><h2>Conclusion</h2>"
        f"<p>{html.escape(profile.conclusion)}</p></section>"
    )


def _call_to_action(profile: ReportProfile) -> str:
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
    active = profile or DEFAULT_REPORT_PROFILE
    findings = [
        item
        for item in assessment.findings
        if not active.selected_areas or item.area in active.selected_areas
    ]
    summary_cards = "".join(
        f"<article><span>{html.escape(key.title())}</span><strong>{value}</strong></article>"
        for key, value in _summary(findings).items()
    )
    renderers = {
        "executive_summary": lambda: _executive_summary(active, findings),
        "priority_actions": lambda: _priority_actions(findings),
        "business_impact": lambda: _business_impact(findings),
        "implementation_roadmap": lambda: _roadmap(findings),
        "assessment_areas": lambda: _assessment_areas(findings),
        "findings": lambda: _findings(findings, active),
        "conclusion": lambda: _conclusion(active),
        "call_to_action": lambda: _call_to_action(active),
    }
    sections = "".join(renderers[name]() for name in active.section_order)
    organisation = html.escape(active.organisation_name)
    report_title = html.escape(active.cover_title or f"{active.organisation_name} assessment report")
    target = html.escape(str(assessment.target))
    generated = html.escape(assessment.generated_at.isoformat())
    accent = html.escape(active.accent_colour, quote=True)
    language = html.escape(active.language, quote=True)
    client = (
        f"<p><strong>Prepared for:</strong> {html.escape(active.client_name)}</p>"
        if active.client_name
        else ""
    )
    introduction = (
        f"<p class='introduction'>{html.escape(active.introduction)}</p>"
        if active.introduction
        else ""
    )
    logo = (
        f"<img class='logo' src='{html.escape(active.logo_data_uri, quote=True)}' alt=''>"
        if active.logo_data_uri
        else ""
    )
    contact = _contact(active)
    contact_html = f"<p class='contact'>{contact}</p>" if contact else ""
    return f"""<!doctype html>
<html lang="{language}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{report_title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef1f4;color:#17191c;font:14px Arial,sans-serif}}
main{{max-width:1300px;margin:32px auto;background:#fff;padding:40px;border:1px solid #dfe3e8}}
.cover{{min-height:320px;border-bottom:4px solid {accent};padding-bottom:28px;margin-bottom:28px;display:flex;flex-direction:column;justify-content:center}}
.logo{{max-width:220px;max-height:90px;object-fit:contain;align-self:flex-start;margin-bottom:24px}}
h1{{margin:0 0 10px;font-size:34px}}h2{{margin-top:28px}}.target{{word-break:break-all;color:#555}}
.meta{{display:flex;flex-wrap:wrap;gap:18px;color:#555}}.contact,.muted{{color:#68707a}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}}
article{{border:1px solid #dfe3e8;padding:16px}}article span{{display:block;text-transform:uppercase;font-size:11px;color:#68707a}}article strong{{display:block;font-size:26px;margin-top:8px}}
.priority-list{{list-style:none;margin:0;padding:0;border:1px solid #dfe3e8}}.priority-list li{{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,.7fr);gap:24px;padding:16px;border-bottom:1px solid #e5e7ea}}
.priority-list span{{display:block;color:#68707a;font-size:11px;text-transform:uppercase}}.priority-list strong{{display:block;margin:5px 0}}.priority-list p{{margin:4px 0;line-height:1.45}}
.roadmap{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.roadmap strong{{font-size:14px}}.roadmap li{{margin-bottom:10px}}
.executive,.introduction,.conclusion,.cta{{padding:18px;border-left:4px solid {accent};background:#f7f8fa}}
.cta a{{display:inline-block;background:{accent};color:#fff;padding:10px 14px;text-decoration:none}}
table{{width:100%;border-collapse:collapse;margin-bottom:28px}}th,td{{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #e5e7ea}}th{{font-size:11px;text-transform:uppercase;color:#68707a}}pre{{white-space:pre-wrap;word-break:break-word;font-size:11px;margin:0}}
.scope{{margin-top:26px;padding:14px;background:#f6f7f9;border-left:3px solid #707780}}
@media(max-width:800px){{main{{margin:0;padding:20px}}.cards{{grid-template-columns:repeat(2,1fr)}}.roadmap,.priority-list li{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}
@media print{{body{{background:#fff}}main{{border:0;margin:0;max-width:none;padding:0}}section,article,tr{{break-inside:avoid}}.cover{{break-after:page}}}}
</style></head><body><main>
<header class="cover">{logo}<h1>{report_title}</h1><div class="target">{target}</div>{client}{contact_html}{introduction}
<div class="meta"><span><strong>Mode:</strong> {html.escape(assessment.mode.title())}</span><span><strong>Generated:</strong> {generated}</span><span><strong>Elapsed:</strong> {assessment.elapsed_ms} ms</span><span><strong>Schema:</strong> {html.escape(assessment.schema_version)}</span></div></header>
<div class="cards">{summary_cards}</div>{sections}<p class="scope">{html.escape(_SCOPE)}</p>
</main></body></html>"""
