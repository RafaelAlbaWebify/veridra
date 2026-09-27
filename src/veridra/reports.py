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
_ES = {
    "Executive summary": "Resumen ejecutivo",
    "Priority actions": "Acciones prioritarias",
    "Business-impact view": "Impacto en el negocio",
    "Implementation roadmap": "Plan de implementación",
    "Assessment areas": "Áreas de evaluación",
    "Evidence-backed findings": "Hallazgos respaldados por evidencia",
    "Conclusion": "Conclusión",
    "Next step": "Siguiente paso",
    "Affected pages": "Páginas afectadas",
    "Status": "Estado",
    "Area": "Área",
    "Finding": "Hallazgo",
    "Observation": "Observación",
    "Recommended action": "Acción recomendada",
    "Evidence": "Evidencia",
    "Passed": "Correctos",
    "Attention": "Requieren atención",
    "Unavailable": "No disponible",
    "Total": "Total",
    "High priority": "Alta prioridad",
    "Example observation": "Ejemplo de observación",
    "Immediate review": "Revisión inmediata",
    "Planned improvement": "Mejora planificada",
    "Monitor or refine": "Supervisar o perfeccionar",
    "Prepared for:": "Preparado para:",
    "Mode:": "Modo:",
    "Generated:": "Generado:",
    "Elapsed:": "Duración:",
    "Schema:": "Esquema:",
}


def _label(profile: ReportProfile, value: str) -> str:
    return _ES.get(value, value) if profile.language == "es" else value



_ES_FINDINGS: dict[str, tuple[str, str]] = {
    "accessibility.document-language": ("Declaración del idioma del documento", "Añade un atributo lang válido al elemento HTML raíz."),
    "accessibility.viewport": ("Declaración de viewport adaptable", "Añade una declaración meta viewport adecuada para una presentación adaptable."),
    "accessibility.form-labels": ("Etiquetas de formulario detectables", "Asocia etiquetas visibles o nombres accesibles a cada control de formulario no oculto."),
    "accessibility.interactive-names": ("Nombres accesibles de enlaces y botones", "Proporciona texto visible o un nombre accesible adecuado para cada control interactivo."),
    "accessibility.image-alt": ("Cobertura de texto alternativo de imágenes", "Añade texto alt significativo, o alt vacío explícito para imágenes decorativas."),
    "accessibility.heading-order": ("Continuidad de la jerarquía de encabezados", "Revisa la jerarquía de encabezados para que comunique una estructura coherente del documento."),
    "accessibility.duplicate-ids": ("Identificadores de elemento únicos", "Haz que los identificadores de elementos sean únicos dentro de cada documento."),
    "crawl.duplicate-titles": ("Títulos de documento duplicados", "Asigna a cada página indexable un título específico y descriptivo."),
    "crawl.duplicate-descriptions": ("Meta descripciones duplicadas", "Escribe una meta descripción útil y específica para cada página indexable."),
    "crawl.image-alt": ("Texto alternativo de imágenes", "Añade texto alt significativo a las imágenes informativas y alt vacío explícito a las decorativas."),
    "crawl.redirect-chains": ("Cadenas de redirección internas", "Actualiza los enlaces internos para que apunten directamente a su destino canónico final."),
    "crawl.page-size": ("Documentos HTML sobredimensionados", "Reduce el HTML innecesario preservando el contenido requerido de la página."),
    "crawl.oversized-html": ("Respuestas HTML sobredimensionadas", "Reduce el HTML generado cuando sea práctico y verifica el tamaño del documento entregado."),
    "crawl.broken-internal-links": ("Enlaces internos rotos", "Actualiza o elimina los enlaces internos que apuntan a destinos no recuperables."),
    "security.cookie-flags": ("Atributos de seguridad de cookies", "Revisa cada cookie y aplica los atributos Secure, HttpOnly y SameSite adecuados."),
    "security.cross-origin-forms": ("Envíos de formularios a otro origen", "Verifica el destino, la propiedad y la finalidad de tratamiento de datos de cada formulario entre orígenes."),
    "security.insecure-form-actions": ("Acciones de formulario inseguras", "Envía datos sensibles y personales únicamente a endpoints HTTPS validados."),
    "security.target-blank-isolation": ("Aislamiento de enlaces en nueva pestaña", "Añade rel=noopener o rel=noreferrer a los enlaces que abren un nuevo contexto de navegación."),
    "security.insecure-resources": ("Recursos activos inseguros", "Migra los subrecursos públicos activos a endpoints HTTPS validados cuando sea compatible."),
    "security.server-disclosure": ("Divulgación de tecnología del servidor", "Reduce la divulgación innecesaria de detalles de implementación en el perímetro público."),
    "security.csp-unsafe-directives": ("Directivas inseguras de Content Security Policy", "Revisa si las directivas CSP inseguras pueden sustituirse por nonces, hashes o políticas más restrictivas."),
}


def _finding_text(profile: ReportProfile, item: Finding) -> tuple[str, str]:
    if profile.language != "es":
        return item.title, item.recommendation or "No action required."
    translated = _ES_FINDINGS.get(item.id)
    if translated is None:
        return item.title, item.recommendation or "No se requiere ninguna acción."
    title, recommendation = translated
    if item.recommendation is None:
        recommendation = "No se requiere ninguna acción."
    return title, recommendation


def affected_urls(item: Finding) -> list[str]:
    values: set[str] = set()
    evidence = item.evidence

    raw_urls = evidence.get("affected_urls", [])
    if isinstance(raw_urls, list):
        values.update(value for value in raw_urls if isinstance(value, str) and value)

    raw_pages = evidence.get("affected_pages", [])
    if isinstance(raw_pages, list):
        values.update(
            url
            for page in raw_pages
            if isinstance(page, dict)
            and isinstance((url := page.get("url")), str)
            and url
        )

    indicators = evidence.get("indicators", [])
    if isinstance(indicators, list):
        values.update(
            url
            for indicator in indicators
            if isinstance(indicator, dict)
            and isinstance((url := indicator.get("url")), str)
            and url
        )

    duplicate_groups = evidence.get("duplicate_groups", [])
    if isinstance(duplicate_groups, list):
        for group in duplicate_groups:
            if not isinstance(group, dict):
                continue
            urls = group.get("urls", [])
            if isinstance(urls, list):
                values.update(url for url in urls if isinstance(url, str) and url)

    conflicts = evidence.get("conflicts", [])
    if isinstance(conflicts, list):
        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            for key in ("first_url", "second_url"):
                url = conflict.get(key)
                if isinstance(url, str) and url:
                    values.add(url)

    for key in ("chains", "redirect_chains"):
        chains = evidence.get(key, [])
        if not isinstance(chains, list):
            continue
        for chain in chains:
            if not isinstance(chain, dict):
                continue
            url = chain.get("final_url")
            if isinstance(url, str) and url:
                values.add(url)

    return sorted(values)


def _affected_pages(item: Finding, profile: ReportProfile) -> str:
    urls = affected_urls(item)
    if not urls:
        return ""
    visible = urls[:10]
    items = "".join(f"<li>{html.escape(url)}</li>" for url in visible)
    remainder = len(urls) - len(visible)
    more = (
        f"<li>+ {remainder} páginas afectadas más</li>"
        if remainder and profile.language == "es"
        else f"<li>+ {remainder} more affected page{'s' if remainder != 1 else ''}</li>"
        if remainder
        else ""
    )
    return (
        f"<div class='affected-pages'><strong>{_label(profile, 'Affected pages')}</strong>"
        f"<ul>{items}{more}</ul></div>"
    )


def _finding_row(item: Finding, profile: ReportProfile, *, show_raw_evidence: bool) -> str:
    evidence_cell = ""
    if show_raw_evidence:
        evidence_json = json.dumps(
            item.evidence,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        evidence_cell = f"<td><pre>{html.escape(evidence_json)}</pre></td>"
    observation = f"{html.escape(item.summary)}{_affected_pages(item, profile)}"
    title, recommendation = _finding_text(profile, item)
    return (
        f"<tr><td>{html.escape(item.status.value)}</td>"
        f"<td>{html.escape(item.area)}</td>"
        f"<td>{html.escape(title)}</td>"
        f"<td>{observation}</td>"
        f"<td>{html.escape(recommendation)}</td>"
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
        (
            f"Esta evaluación identificó {len(attention)} hallazgos que requieren atención "
            f"en {areas} áreas, incluidos {high} de alta prioridad. "
            "Las prioridades se derivan del estado y la severidad de los hallazgos; "
            "no se utiliza una puntuación sintética."
        )
        if profile.language == "es"
        else (
            f"This assessment identified {len(attention)} attention findings across "
            f"{areas} areas, including {high} high-priority observations. "
            "Priorities are derived from finding status and severity; no synthetic score is used."
        )
    )
    text = profile.executive_summary or generated
    return (
        f"<section class='executive'><h2>{_label(profile, 'Executive summary')}</h2>"
        f"<p>{html.escape(text)}</p></section>"
    )


def _priority_actions(findings: list[Finding], profile: ReportProfile) -> str:
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
        f"<section><h2>{_label(profile, 'Priority actions')}</h2>"
        "<p class='muted'>Attention findings ordered by explicit severity and area.</p>"
        f"<ol class='priority-list'>{content}</ol></section>"
    )


def _business_impact(findings: list[Finding], profile: ReportProfile) -> str:
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
        f"<section><h2>{_label(profile, 'Business-impact view')}</h2>"
        "<p class='muted'>A transparent grouping of observed findings, not a financial-impact estimate.</p>"
        f"<table><thead><tr><th>{_label(profile, 'Area')}</th>"
        f"<th>{_label(profile, 'Attention')}</th><th>{_label(profile, 'High priority')}</th>"
        f"<th>{_label(profile, 'Example observation')}</th></tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _roadmap(findings: list[Finding], profile: ReportProfile) -> str:
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
        columns.append(f"<article><h3>{_label(profile, heading)}</h3><ul>{entries}</ul></article>")
    return (
        f"<section><h2>{_label(profile, 'Implementation roadmap')}</h2>"
        "<p class='muted'>Suggested sequencing derived from explicit finding severity; owners and deadlines remain operator decisions.</p>"
        f"<div class='roadmap'>{''.join(columns)}</div></section>"
    )


def _assessment_areas(findings: list[Finding], profile: ReportProfile) -> str:
    rows = "".join(
        _area_row(area, values) for area, values in _area_summary(findings).items()
    )
    return (
        f"<section><h2>{_label(profile, 'Assessment areas')}</h2><table><thead><tr>"
        f"<th>{_label(profile, 'Area')}</th><th>{_label(profile, 'Passed')}</th>"
        f"<th>{_label(profile, 'Attention')}</th><th>{_label(profile, 'Unavailable')}</th>"
        f"<th>{_label(profile, 'Total')}</th></tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _findings(findings: list[Finding], profile: ReportProfile) -> str:
    rows = "".join(
        _finding_row(item, profile, show_raw_evidence=profile.show_raw_evidence)
        for item in findings
    ) or "<tr><td colspan='6'>No findings are included in this template.</td></tr>"
    evidence_heading = (
        f"<th>{_label(profile, 'Evidence')}</th>" if profile.show_raw_evidence else ""
    )
    return (
        f"<section><h2>{_label(profile, 'Evidence-backed findings')}</h2>"
        f"<table><thead><tr><th>{_label(profile, 'Status')}</th>"
        f"<th>{_label(profile, 'Area')}</th><th>{_label(profile, 'Finding')}</th>"
        f"<th>{_label(profile, 'Observation')}</th>"
        f"<th>{_label(profile, 'Recommended action')}</th>{evidence_heading}</tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def _conclusion(profile: ReportProfile) -> str:
    if not profile.conclusion:
        return ""
    return (
        f"<section class='conclusion'><h2>{_label(profile, 'Conclusion')}</h2>"
        f"<p>{html.escape(profile.conclusion)}</p></section>"
    )


def _call_to_action(profile: ReportProfile) -> str:
    if not profile.call_to_action_label or not profile.call_to_action_url:
        return ""
    return (
        f"<section class='cta'><h2>{_label(profile, 'Next step')}</h2>"
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
        "priority_actions": lambda: _priority_actions(findings, active),
        "business_impact": lambda: _business_impact(findings, active),
        "implementation_roadmap": lambda: _roadmap(findings, active),
        "assessment_areas": lambda: _assessment_areas(findings, active),
        "findings": lambda: _findings(findings, active),
        "conclusion": lambda: _conclusion(active),
        "call_to_action": lambda: _call_to_action(active),
    }
    sections = "".join(renderers[name]() for name in active.section_order)
    organisation = html.escape(active.organisation_name)
    organisation_attr = html.escape(active.organisation_name, quote=True)
    report_title = html.escape(
        active.cover_title or f"{active.organisation_name} assessment report"
    )
    target = html.escape(str(assessment.target))
    generated = html.escape(assessment.generated_at.isoformat())
    accent = html.escape(active.accent_colour, quote=True)
    language = html.escape(active.language, quote=True)
    client = (
        f"<p><strong>{_label(active, 'Prepared for:')}</strong> {html.escape(active.client_name)}</p>"
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
<meta name="veridra-report-brand" content="{organisation_attr}">
<title>{report_title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef1f4;color:#17191c;font:14px Arial,sans-serif}}
main{{max-width:1300px;margin:32px auto;background:#fff;padding:40px;border:1px solid #dfe3e8}}
.cover{{min-height:320px;border-bottom:4px solid {accent};padding-bottom:28px;margin-bottom:28px;display:flex;flex-direction:column;justify-content:center}}
.logo{{max-width:220px;max-height:90px;object-fit:contain;align-self:flex-start;margin-bottom:24px}}
.organisation{{margin:0 0 8px;color:#68707a;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}}
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
<header class="cover">{logo}<p class="organisation">{organisation}</p><h1>{report_title}</h1><div class="target">{target}</div>{client}{contact_html}{introduction}
<div class="meta"><span><strong>{_label(active, "Mode:")}</strong> {html.escape(assessment.mode.title())}</span><span><strong>{_label(active, "Generated:")}</strong> {generated}</span><span><strong>{_label(active, "Elapsed:")}</strong> {assessment.elapsed_ms} ms</span><span><strong>{_label(active, "Schema:")}</strong> {html.escape(assessment.schema_version)}</span></div></header>
<div class="cards">{summary_cards}</div>{sections}<p class="scope">{html.escape(_SCOPE)}</p>
</main></body></html>"""
