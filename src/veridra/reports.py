from __future__ import annotations

import html
import json
from collections import Counter, defaultdict

from .core import Assessment, Finding, Status
from .progress import ProgressSummary
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile

_SCOPE = (
    "Scope: bounded public checks only. This is not a penetration test and "
    "does not inspect authenticated functionality, source code, server "
    "configuration, or private infrastructure."
)
_SCOPE_ES = (
    "Alcance: únicamente comprobaciones públicas acotadas. Esto no es una prueba "
    "de penetración y no inspecciona funcionalidades autenticadas, código fuente, "
    "configuración del servidor ni infraestructura privada."
)
_ES_AREAS = {
    "Accessibility": "Accesibilidad",
    "Search visibility": "Visibilidad en buscadores",
    "Website health": "Salud del sitio web",
    "Security posture": "Postura de seguridad",
    "Trust and content quality": "Confianza y calidad del contenido",
    "Local presence": "Presencia local",
}
_ES_STATUS = {"passed": "correcto", "attention": "requiere atención", "unavailable": "no disponible"}
_ES_SEVERITY = {"critical": "crítica", "high": "alta", "medium": "media", "low": "baja", "info": "informativa"}
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
    "Progress since previous assessment": "Progreso desde la evaluación anterior",
    "Resolved findings": "Hallazgos resueltos",
    "New findings": "Hallazgos nuevos",
    "Persistent findings": "Hallazgos persistentes",
    "Pages changed": "Páginas modificadas",
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
    "Contents": "Índice",
    "Assessment overview": "Resumen de la evaluación",
    "Finding status distribution": "Distribución del estado de los hallazgos",
}


def spanish_finding_translation_ids() -> frozenset[str]:
    return frozenset(_ES_FINDINGS)


def _area(profile: ReportProfile, value: str) -> str:
    return _ES_AREAS.get(value, value) if profile.language == "es" else value


def _status(profile: ReportProfile, value: str) -> str:
    return _ES_STATUS.get(value, value) if profile.language == "es" else value


def _severity(profile: ReportProfile, value: str) -> str:
    lowered = value.lower()
    if profile.language == "es":
        return _ES_SEVERITY.get(lowered, value)
    return value.title()


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
    "crawl.http-status": ("Respuesta multipágina", "Revisa y corrige las páginas afectadas por respuestas HTTP que requieren atención."),
    "crawl.title": ("Título de documento multipágina", "Revisa y corrige los títulos de las páginas afectadas."),
    "crawl.description": ("Meta description multipágina", "Revisa y corrige las meta descriptions de las páginas afectadas."),
    "crawl.h1": ("Encabezado principal multipágina", "Revisa y corrige el encabezado principal de las páginas afectadas."),
    "crawl.canonical": ("URL canónica multipágina", "Revisa y corrige las URLs canónicas de las páginas afectadas."),
    "crawl.mixed-content": ("Contenido mixto multipágina", "Revisa y corrige las referencias HTTP activas de las páginas afectadas."),
    "crawl.retrieval-coverage": ("Cobertura de recuperación del rastreo", "Revisa las URLs bloqueadas, fallidas, no analizables u omitidas por límites antes de interpretar la ausencia de hallazgos como prueba de que esas páginas están correctas."),

    "content.placeholder-default": ("Contenido público predeterminado o provisional", "Sustituye el contenido público predeterminado o provisional confirmado por información empresarial precisa."),
    "content.explicit-update-age": ("Indicador explícito de antigüedad de actualización", "Confirma si el contenido fechado sigue siendo correcto y actualiza la etiqueta pública solo después de revisarlo."),
    "content.opening-hours-consistency": ("Coherencia de horarios entre páginas", "Confirma los horarios oficiales con el propietario y haz coherentes las páginas orientadas al cliente."),
    "security.cookie-flags": ("Atributos de seguridad de cookies", "Revisa cada cookie y aplica los atributos Secure, HttpOnly y SameSite adecuados."),
    "security.cross-origin-forms": ("Envíos de formularios a otro origen", "Verifica el destino, la propiedad y la finalidad de tratamiento de datos de cada formulario entre orígenes."),
    "security.insecure-form-actions": ("Acciones de formulario inseguras", "Envía datos sensibles y personales únicamente a endpoints HTTPS validados."),
    "security.target-blank-isolation": ("Aislamiento de enlaces en nueva pestaña", "Añade rel=noopener o rel=noreferrer a los enlaces que abren un nuevo contexto de navegación."),
    "security.insecure-resources": ("Recursos activos inseguros", "Migra los subrecursos públicos activos a endpoints HTTPS validados cuando sea compatible."),
    "security.server-disclosure": ("Divulgación de tecnología del servidor", "Reduce la divulgación innecesaria de detalles de implementación en el perímetro público."),
    "security.csp-unsafe-directives": ("Directivas inseguras de Content Security Policy", "Revisa si las directivas CSP inseguras pueden sustituirse por nonces, hashes o políticas más restrictivas."),
    "health.http-status": ("Respuesta de la página de inicio", "Investiga la respuesta y disponibilidad de la página de inicio pública."),
    "search.robots-availability": ("Disponibilidad de robots.txt", "Confirma si debería estar disponible un archivo robots.txt público."),
    "crawl.effective-limits": ("Límites efectivos del rastreo", "No se requiere ninguna acción."),
    "search.indexable": ("Meta robots indexable", "Elimina noindex cuando la página deba aparecer en buscadores."),
    "search.sitemap": ("Declaración del sitemap", "Declara el sitemap XML en robots.txt."),
    "ai.structured-data": ("Datos estructurados de entidad", "Añade JSON-LD preciso de Organisation o Service."),
    "ai.open-graph-title": ("Título Open Graph", "Añade un valor og:title preciso."),
    "ai.open-graph-description": ("Descripción Open Graph", "Añade un valor og:description preciso."),
    "trust.about": ("Información «Sobre nosotros» en la página de inicio", "Muestra información de la organización claramente etiquetada desde la página de inicio."),
    "trust.contact": ("Ruta de contacto desde la página de inicio", "Muestra una ruta de contacto claramente etiquetada desde la página de inicio."),
    "trust.privacy": ("Ruta de privacidad desde la página de inicio", "Muestra una ruta de privacidad o protección de datos claramente etiquetada desde la página de inicio."),
    "trust.terms": ("Ruta de términos desde la página de inicio", "Muestra los términos o la información legal aplicable desde la página de inicio cuando corresponda."),
    "security.hsts": ("Strict-Transport-Security", "Implementa HSTS después de validar HTTPS."),
    "security.csp": ("Content-Security-Policy", "Introduce y prueba una CSP."),
    "security.nosniff": ("X-Content-Type-Options", "Configura X-Content-Type-Options: nosniff."),
    "security.frames": ("Protección frente a framing", "Configura frame-ancestors en CSP o X-Frame-Options."),
    "security.referrer": ("Referrer-Policy", "Configura una Referrer-Policy adecuada."),
    "security.permissions": ("Permissions-Policy", "Configura una Permissions-Policy restrictiva cuando corresponda."),
    "dns.nameservers": ("Servidores de nombres autoritativos", "Usa al menos dos servidores de nombres autoritativos en infraestructura independiente."),
    "email.mx": ("Registros de intercambio de correo", "Publica registros MX cuando el dominio deba recibir correo, o documenta que no admite correo de forma intencionada."),
    "email.spf": ("Política SPF", "Publica exactamente un registro SPF y consolida en él todos los remitentes permitidos."),
    "email.dmarc": ("Política DMARC", "Publica un registro DMARC válido y progresa de monitorización a quarantine o reject cuando proceda."),
    "local.structured-business": ("Datos estructurados LocalBusiness", "Añade JSON-LD LocalBusiness preciso usando el subtipo aplicable más específico."),
    "local.structured-name": ("Nombre comercial estructurado", "Añade el nombre comercial público a los datos estructurados LocalBusiness."),
    "local.structured-url": ("URL del sitio web estructurada", "Añade la URL pública canónica a los datos estructurados LocalBusiness."),
    "local.structured-phone": ("Teléfono estructurado", "Añade el número de teléfono público principal a los datos estructurados LocalBusiness."),
    "local.structured-address": ("Dirección postal estructurada", "Añade una PostalAddress completa a los datos estructurados LocalBusiness."),
    "local.structured-hours": ("Horario estructurado", "Añade datos openingHours u openingHoursSpecification precisos."),
    "local.structured-same-as": ("Referencias de perfiles estructuradas", "Añade URLs de perfiles públicos verificados mediante sameAs cuando corresponda."),
    "local.visible-phone": ("Ruta de teléfono visible", "Publica un número de teléfono público claro y clicable donde los clientes esperen encontrarlo."),
    "local.visible-address": ("Señal de dirección visible", "Publica la dirección del negocio o explica claramente el área de servicio."),
    "local.visible-hours": ("Señal de horario visible", "Publica horarios de apertura o información de disponibilidad precisos."),
    "local.map-link": ("Ruta de mapa o indicaciones", "Proporciona un enlace claro a un mapa o indicaciones para los clientes que visiten la ubicación."),
    "local.location-route": ("Ruta de información de ubicación", "Añade una ruta claramente etiquetada de ubicación, indicaciones o cómo llegar."),
    "ai.oai-searchbot": ("Acceso de OAI-SearchBot", "Revisa robots.txt si este rastreador debe acceder al contenido público."),
    "ai.gptbot": ("Acceso de GPTBot", "Revisa robots.txt si este rastreador debe acceder al contenido público."),
    "ai.google-extended": ("Acceso de Google-Extended", "Revisa robots.txt si este rastreador debe acceder al contenido público."),
    "ai.googlebot": ("Acceso de Googlebot", "Revisa robots.txt si este rastreador debe acceder al contenido público."),


}


_ES_SUMMARIES: dict[str, tuple[str, str]] = {
    "accessibility.document-language": ("{count} páginas rastreadas no declaran el idioma HTML.", "Todas las páginas rastreadas declaran el idioma HTML."),
    "accessibility.viewport": ("{count} páginas rastreadas no exponen una declaración meta viewport.", "Todas las páginas rastreadas exponen una declaración meta viewport."),
    "accessibility.form-labels": ("{count} páginas rastreadas contienen controles de formulario sin una etiqueta detectable.", "No se detectaron controles de formulario sin etiqueta en las páginas rastreadas."),
    "accessibility.interactive-names": ("{count} páginas rastreadas contienen enlaces o botones sin nombres detectables.", "No se detectaron enlaces ni botones sin nombre en las páginas rastreadas."),
    "accessibility.image-alt": ("{count} páginas rastreadas contienen imágenes sin atributo alt.", "No se detectaron imágenes sin atributo alt en las páginas rastreadas."),
    "accessibility.heading-order": ("{count} páginas rastreadas contienen un salto en la jerarquía de encabezados.", "No se detectaron saltos en la jerarquía de encabezados en las páginas rastreadas."),
    "accessibility.duplicate-ids": ("{count} páginas rastreadas contienen IDs de elemento duplicados.", "No se detectaron IDs de elemento duplicados en las páginas rastreadas."),
    "security.cookie-flags": ("{count} páginas rastreadas establecen cookies sin todos los atributos de seguridad detectados.", "No se detectaron cookies con atributos de seguridad incompletos en las páginas rastreadas."),
    "security.cross-origin-forms": ("{count} páginas rastreadas envían formularios a un hostname diferente.", "No se detectaron formularios enviados a otro hostname en las páginas rastreadas."),
    "security.insecure-form-actions": ("{count} páginas rastreadas exponen una acción de formulario HTTP.", "No se detectaron acciones de formulario HTTP en las páginas rastreadas."),
    "security.target-blank-isolation": ("{count} páginas rastreadas contienen enlaces target=_blank sin protección detectable.", "No se detectaron enlaces target=_blank sin protección en las páginas rastreadas."),
    "security.insecure-resources": ("{count} páginas rastreadas referencian subrecursos HTTP activos.", "No se detectaron subrecursos HTTP activos en las páginas rastreadas."),
    "security.server-disclosure": ("{count} páginas rastreadas exponen valores Server o X-Powered-By.", "No se detectó divulgación Server o X-Powered-By en las páginas rastreadas."),
    "security.csp-unsafe-directives": ("{count} páginas rastreadas exponen una CSP con directivas inseguras.", "No se detectaron directivas CSP inseguras en las páginas rastreadas."),
    "content.placeholder-default": ("{count} páginas rastreadas contienen un patrón predeterminado o provisional.", "No se observó contenido predeterminado o provisional configurado en el rastreo acotado."),
    "content.explicit-update-age": ("{count} páginas rastreadas indican explícitamente una última actualización de hace al menos 18 meses. Es un indicador de antigüedad, no prueba de que el contenido sea incorrecto.", "No se observó ninguna etiqueta explícita de actualización de al menos 18 meses en el rastreo acotado."),
    "content.opening-hours-consistency": ("Se detectaron {count} comparaciones de páginas u horarios con horas contradictorias para al menos un día de la semana.", "No se observaron horarios contradictorios entre las páginas del rastreo acotado."),
    "dns.nameservers": ("Se encontraron {count} registros de servidores de nombres autoritativos.", "Se encontraron {count} registros de servidores de nombres autoritativos."),
    "email.mx": ("No se devolvieron registros públicos de intercambio de correo.", "Hay registros públicos de intercambio de correo."),
    "email.spf": ("Se esperaba exactamente una política SPF; se encontraron {count}.", "Se encontró exactamente una política SPF."),
    "local.structured-business": ("Los datos estructurados LocalBusiness no son evidentes en ninguna de las {count} páginas evaluadas.", "Los datos estructurados LocalBusiness son evidentes en al menos una página evaluada."),
    "local.structured-name": ("El nombre comercial estructurado no es evidente en ninguna de las {count} páginas evaluadas.", "El nombre comercial estructurado es evidente en al menos una página evaluada."),
    "local.structured-url": ("La URL estructurada del sitio web no es evidente en ninguna de las {count} páginas evaluadas.", "La URL estructurada del sitio web es evidente en al menos una página evaluada."),
    "local.structured-phone": ("El teléfono estructurado no es evidente en ninguna de las {count} páginas evaluadas.", "El teléfono estructurado es evidente en al menos una página evaluada."),
    "local.structured-address": ("La dirección postal estructurada no es evidente en ninguna de las {count} páginas evaluadas.", "La dirección postal estructurada es evidente en al menos una página evaluada."),
    "local.structured-hours": ("El horario estructurado no es evidente en ninguna de las {count} páginas evaluadas.", "El horario estructurado es evidente en al menos una página evaluada."),
    "local.structured-same-as": ("Las referencias de perfiles estructuradas no son evidentes en ninguna de las {count} páginas evaluadas.", "Las referencias de perfiles estructuradas son evidentes en al menos una página evaluada."),
    "local.visible-phone": ("No se detectó una ruta de teléfono visible en ninguna de las {count} páginas evaluadas.", "Se detectó una ruta de teléfono visible en al menos una página evaluada."),
    "local.visible-address": ("No se detectó una señal de dirección visible en ninguna de las {count} páginas evaluadas.", "Se detectó una señal de dirección visible en al menos una página evaluada."),
    "local.visible-hours": ("No se detectó una señal de horario visible en ninguna de las {count} páginas evaluadas.", "Se detectó una señal de horario visible en al menos una página evaluada."),
    "local.map-link": ("No se detectó una ruta de mapa o indicaciones en ninguna de las {count} páginas evaluadas.", "Se detectó una ruta de mapa o indicaciones en al menos una página evaluada."),
    "local.location-route": ("No se detectó una ruta de información de ubicación en ninguna de las {count} páginas evaluadas.", "Se detectó una ruta de información de ubicación en al menos una página evaluada."),
    "crawl.http-status": ("{count} páginas HTML rastreadas requieren atención en esta comprobación.", "Todas las páginas HTML rastreadas superaron esta comprobación."),
    "crawl.title": ("{count} páginas HTML rastreadas requieren atención en esta comprobación.", "Todas las páginas HTML rastreadas superaron esta comprobación."),
    "crawl.description": ("{count} páginas HTML rastreadas requieren atención en esta comprobación.", "Todas las páginas HTML rastreadas superaron esta comprobación."),
    "crawl.h1": ("{count} páginas HTML rastreadas requieren atención en esta comprobación.", "Todas las páginas HTML rastreadas superaron esta comprobación."),
    "crawl.canonical": ("{count} páginas HTML rastreadas requieren atención en esta comprobación.", "Todas las páginas HTML rastreadas superaron esta comprobación."),
    "crawl.mixed-content": ("{count} páginas HTML rastreadas requieren atención en esta comprobación.", "Todas las páginas HTML rastreadas superaron esta comprobación."),


}


def _finding_count(item: Finding) -> int:
    evidence = item.evidence
    keyed_counts = {
        "content.opening-hours-consistency": "conflicts",
        "content.explicit-update-age": "indicators",
        "crawl.duplicate-titles": "duplicate_groups",
        "crawl.duplicate-descriptions": "duplicate_groups",
        "crawl.redirect-chains": "chains",
        "crawl.oversized-html": "affected_pages",
        "crawl.page-size": "affected_pages",
        "dns.nameservers": "nameservers",
        "email.spf": "spf_records",
        "crawl.http-status": "affected_urls",
        "crawl.title": "affected_urls",
        "crawl.description": "affected_urls",
        "crawl.h1": "affected_urls",
        "crawl.canonical": "affected_urls",
        "crawl.mixed-content": "affected_urls",
    }
    key = keyed_counts.get(item.id)
    if key is not None:
        values = evidence.get(key, [])
        if isinstance(values, list):
            return len(values)
    page_count = evidence.get("assessed_page_count")
    if isinstance(page_count, int):
        return page_count
    return len(affected_urls(item))


def _special_spanish_summary(item: Finding) -> str | None:
    evidence = item.evidence
    if item.id == "crawl.retrieval-coverage":
        summary = evidence.get("crawl_summary", {})
        if not isinstance(summary, dict):
            return None
        attempted = summary.get("attempted_pages", 0)
        skipped = summary.get("skipped_pages", 0)
        blocked = evidence.get("blocked_urls", [])
        failed = evidence.get("failed_urls", [])
        if item.status == Status.passed:
            return (
                f"Las {attempted} URLs intentadas durante el rastreo se recuperaron "
                "dentro de los límites configurados de la evaluación."
            )
        return (
            f"Se analizaron {evidence.get('crawled_pages', 0)} páginas HTML, con "
            f"{len(blocked) if isinstance(blocked, list) else 0} bloqueadas, "
            f"{len(failed) if isinstance(failed, list) else 0} fallidas y "
            f"{skipped} recuperaciones omitidas o no analizables."
        )
    if item.id in {"ai.oai-searchbot", "ai.gptbot", "ai.google-extended", "ai.googlebot"}:
        blocked = bool(evidence.get("disallow_all"))
        title = _ES_FINDINGS[item.id][0]
        return f"{title} está {'bloqueado' if blocked else 'permitido'} por robots.txt."
    return None


def _finding_summary(profile: ReportProfile, item: Finding) -> str:
    if profile.language != "es":
        return item.summary
    special = _special_spanish_summary(item)
    if special is not None:
        return special
    templates = _ES_SUMMARIES.get(item.id)
    if templates is None:
        return item.summary
    attention_template, passed_template = templates
    if item.status == Status.passed:
        return passed_template
    return attention_template.format(count=_finding_count(item))


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
    observation = f"{html.escape(_finding_summary(profile, item))}{_affected_pages(item, profile)}"
    title, recommendation = _finding_text(profile, item)
    return (
        f"<tr><td>{html.escape(_status(profile, item.status.value))}</td>"
        f"<td>{html.escape(_area(profile, item.area))}</td>"
        f"<td>{html.escape(title)}</td>"
        f"<td>{observation}</td>"
        f"<td>{html.escape(recommendation)}</td>"
        f"{evidence_cell}</tr>"
    )


def _priority_item(item: Finding, profile: ReportProfile) -> str:
    title, localized_recommendation = _finding_text(profile, item)
    recommendation = html.escape(localized_recommendation)
    return (
        "<li>"
        f"<div><span>{html.escape(_area(profile, item.area))} · {html.escape(_severity(profile, item.severity))}</span>"
        f"<strong>{html.escape(title)}</strong>"
        f"<p>{html.escape(_finding_summary(profile, item))}</p></div>"
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


_SECTION_HEADINGS = {
    "executive_summary": "Executive summary",
    "priority_actions": "Priority actions",
    "business_impact": "Business-impact view",
    "implementation_roadmap": "Implementation roadmap",
    "assessment_areas": "Assessment areas",
    "findings": "Evidence-backed findings",
    "conclusion": "Conclusion",
    "call_to_action": "Next step",
}


def _section_anchor(name: str) -> str:
    return "report-" + name.replace("_", "-")


def _anchored_section(name: str, fragment: str) -> str:
    if not fragment:
        return ""
    anchor = _section_anchor(name)
    if fragment.startswith("<section class='"):
        return fragment.replace(
            "<section class='",
            f"<section id='{anchor}' class='report-section ",
            1,
        )
    return fragment.replace(
        "<section>",
        f"<section id='{anchor}' class='report-section'>",
        1,
    )


def _contents(
    profile: ReportProfile,
    entries: list[tuple[str, str]],
) -> str:
    items = "".join(
        f"<li><a href='#{_section_anchor(name)}'>{html.escape(_label(profile, label))}</a></li>"
        for name, label in entries
    )
    return (
        f"<nav class='toc' aria-label='{html.escape(_label(profile, 'Contents'), quote=True)}'>"
        f"<h2>{html.escape(_label(profile, 'Contents'))}</h2><ol>{items}</ol></nav>"
    )


def _status_overview(findings: list[Finding], profile: ReportProfile) -> str:
    counts = _summary(findings)
    total = counts["total"]
    denominator = max(total, 1)
    segments = "".join(
        f"<span class='status-{key}' style='width:{(counts[key] / denominator) * 100:.4f}%'></span>"
        for key in ("passed", "attention", "unavailable")
        if counts[key] > 0
    )
    legend = "".join(
        f"<li><span class='legend-dot status-{key}'></span>"
        f"{html.escape(_label(profile, key.title()))}: <strong>{counts[key]}</strong></li>"
        for key in ("passed", "attention", "unavailable")
    )
    aria = ", ".join(
        f"{_label(profile, key.title())} {counts[key]}"
        for key in ("passed", "attention", "unavailable")
    )
    limitation = (
        "Distribución de estados observados; no es una puntuación sintética."
        if profile.language == "es"
        else "Distribution of observed finding states; this is not a synthetic score."
    )
    return (
        f"<section id='{_section_anchor('overview')}' class='report-section overview'>"
        f"<h2>{html.escape(_label(profile, 'Assessment overview'))}</h2>"
        f"<div class='cards'>"
        + "".join(
            f"<article><span>{html.escape(_label(profile, key.title()))}</span><strong>{value}</strong></article>"
            for key, value in counts.items()
        )
        + "</div>"
        f"<h3>{html.escape(_label(profile, 'Finding status distribution'))}</h3>"
        f"<div class='status-bar' role='img' aria-label='{html.escape(aria, quote=True)}'>{segments}</div>"
        f"<ul class='status-legend'>{legend}</ul>"
        f"<p class='muted'>{html.escape(limitation)}</p></section>"
    )


def _summary(findings: list[Finding]) -> dict[str, int]:
    counts = Counter(item.status.value for item in findings)
    return {
        "passed": counts.get("passed", 0),
        "attention": counts.get("attention", 0),
        "unavailable": counts.get("unavailable", 0),
        "total": len(findings),
    }


def _area_row(area: str, values: dict[str, int], profile: ReportProfile) -> str:
    return (
        f"<tr><td>{html.escape(_area(profile, area))}</td>"
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
    content = "".join(_priority_item(item, profile) for item in attention)
    if not content:
        content = (
            "<p class='muted'>Actualmente no hay hallazgos que requieran atención prioritaria.</p>"
            if profile.language == "es"
            else "<p class='muted'>No attention findings are currently prioritised.</p>"
        )
    explanation = (
        "Hallazgos que requieren atención ordenados por severidad explícita y área."
        if profile.language == "es"
        else "Attention findings ordered by explicit severity and area."
    )
    return (
        f"<section><h2>{_label(profile, 'Priority actions')}</h2>"
        f"<p class='muted'>{explanation}</p>"
        f"<ol class='priority-list'>{content}</ol></section>"
    )


def _business_impact(findings: list[Finding], profile: ReportProfile) -> str:
    attention = [item for item in findings if item.status == Status.attention]
    grouped: defaultdict[str, list[Finding]] = defaultdict(list)
    for item in attention:
        grouped[item.area].append(item)
    rows = "".join(
        "<tr><td>{area}</td><td>{count}</td><td>{high}</td><td>{summary}</td></tr>".format(
            area=html.escape(_area(profile, area)),
            count=len(items),
            high=sum(
                item.severity.lower() in {"critical", "high"} for item in items
            ),
            summary=html.escape(_finding_summary(profile, items[0])),
        )
        for area, items in sorted(grouped.items())
    )
    if not rows:
        rows = (
            "<tr><td colspan='4'>No hay hallazgos que requieran atención.</td></tr>"
            if profile.language == "es"
            else "<tr><td colspan='4'>No attention findings are available.</td></tr>"
        )
    explanation = (
        "Agrupación transparente de los hallazgos observados; no es una estimación del impacto financiero."
        if profile.language == "es"
        else "A transparent grouping of observed findings, not a financial-impact estimate."
    )
    return (
        f"<section><h2>{_label(profile, 'Business-impact view')}</h2>"
        f"<p class='muted'>{explanation}</p>"
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
            (
                f"<li><strong>{html.escape(_finding_text(profile, item)[0])}</strong><br>"
                f"{html.escape(_finding_text(profile, item)[1])}</li>"
            )
            for item in items
        ) or (
            "<li>No hay hallazgos que requieran atención en esta categoría.</li>"
            if profile.language == "es"
            else "<li>No matching attention findings.</li>"
        )
        columns.append(f"<article><h3>{_label(profile, heading)}</h3><ul>{entries}</ul></article>")
    explanation = (
        "Secuencia sugerida a partir de la severidad explícita de los hallazgos; responsables y plazos siguen siendo decisiones del operador."
        if profile.language == "es"
        else "Suggested sequencing derived from explicit finding severity; owners and deadlines remain operator decisions."
    )
    return (
        f"<section><h2>{_label(profile, 'Implementation roadmap')}</h2>"
        f"<p class='muted'>{explanation}</p>"
        f"<div class='roadmap'>{''.join(columns)}</div></section>"
    )


def _assessment_areas(findings: list[Finding], profile: ReportProfile) -> str:
    rows = "".join(
        _area_row(area, values, profile) for area, values in _area_summary(findings).items()
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
    ) or (
        "<tr><td colspan='6'>No se incluyen hallazgos en esta plantilla.</td></tr>"
        if profile.language == "es"
        else "<tr><td colspan='6'>No findings are included in this template.</td></tr>"
    )
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


def _progress_section(profile: ReportProfile, progress: ProgressSummary | None) -> str:
    if progress is None:
        return ""
    cards = "".join(
        (
            f"<article><span>{_label(profile, 'Resolved findings')}</span><strong>{len(progress.resolved_findings)}</strong></article>",
            f"<article><span>{_label(profile, 'New findings')}</span><strong>{len(progress.new_findings)}</strong></article>",
            f"<article><span>{_label(profile, 'Persistent findings')}</span><strong>{len(progress.persistent_findings)}</strong></article>",
            f"<article><span>{_label(profile, 'Pages changed')}</span><strong>{len(progress.pages_changed)}</strong></article>",
        )
    )
    limitation = (
        "Comparación determinista con la evaluación guardada inmediatamente anterior. No implica cambios de tráfico, ranking ni rendimiento comercial."
        if profile.language == "es"
        else "Deterministic comparison with the immediately previous saved assessment. It does not imply changes in traffic, ranking or commercial performance."
    )
    return (
        f"<section><h2>{_label(profile, 'Progress since previous assessment')}</h2>"
        f"<div class='cards'>{cards}</div><p class='muted'>{html.escape(limitation)}</p></section>"
    )


def render_report(
    assessment: Assessment,
    profile: ReportProfile | None = None,
    *,
    progress: ProgressSummary | None = None,
) -> str:
    active = profile or DEFAULT_REPORT_PROFILE
    findings = [
        item
        for item in assessment.findings
        if not active.selected_areas or item.area in active.selected_areas
    ]
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
    rendered: list[tuple[str, str, str]] = [
        ("overview", "Assessment overview", _status_overview(findings, active))
    ]
    progress_section = _progress_section(active, progress)
    if progress_section:
        rendered.append(
            (
                "progress",
                "Progress since previous assessment",
                _anchored_section("progress", progress_section),
            )
        )
    for name in active.section_order:
        fragment = renderers[name]()
        if fragment:
            rendered.append(
                (
                    name,
                    _SECTION_HEADINGS[name],
                    _anchored_section(name, fragment),
                )
            )
    contents = _contents(
        active,
        [(name, label) for name, label, _ in rendered],
    )
    sections = "".join(fragment for _, _, fragment in rendered)
    organisation = html.escape(active.organisation_name)
    organisation_attr = html.escape(active.organisation_name, quote=True)
    report_title = html.escape(
        active.cover_title
        or (
            f"Informe de evaluación de {active.organisation_name}"
            if active.language == "es"
            else f"{active.organisation_name} assessment report"
        )
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
.toc{{margin:0 0 28px;padding:18px 22px;border:1px solid #dfe3e8;background:#fafbfc}}.toc h2{{margin-top:0}}.toc ol{{columns:2;column-gap:36px;margin:0;padding-left:20px}}.toc li{{margin:7px 0;break-inside:avoid}}.toc a{{color:#17191c;text-decoration:none}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}}
article{{border:1px solid #dfe3e8;padding:16px}}article span{{display:block;text-transform:uppercase;font-size:11px;color:#68707a}}article strong{{display:block;font-size:26px;margin-top:8px}}
.status-bar{{height:18px;width:100%;display:flex;overflow:hidden;border:1px solid #dfe3e8;border-radius:999px;background:#eef1f4}}.status-bar>span{{display:block;height:100%}}.status-passed{{background:#3f7d5a}}.status-attention{{background:{accent}}}.status-unavailable{{background:#9aa2ab}}.status-legend{{display:flex;gap:18px;flex-wrap:wrap;list-style:none;padding:0;margin:10px 0}}.status-legend li{{display:flex;align-items:center;gap:7px}}.legend-dot{{width:10px;height:10px;border-radius:50%;display:inline-block}}
.priority-list{{list-style:none;margin:0;padding:0;border:1px solid #dfe3e8}}.priority-list li{{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,.7fr);gap:24px;padding:16px;border-bottom:1px solid #e5e7ea}}
.priority-list span{{display:block;color:#68707a;font-size:11px;text-transform:uppercase}}.priority-list strong{{display:block;margin:5px 0}}.priority-list p{{margin:4px 0;line-height:1.45}}
.roadmap{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.roadmap strong{{font-size:14px}}.roadmap li{{margin-bottom:10px}}
.executive,.introduction,.conclusion,.cta{{padding:18px;border-left:4px solid {accent};background:#f7f8fa}}
.cta a{{display:inline-block;background:{accent};color:#fff;padding:10px 14px;text-decoration:none}}
table{{width:100%;border-collapse:collapse;margin-bottom:28px}}th,td{{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #e5e7ea}}th{{font-size:11px;text-transform:uppercase;color:#68707a}}pre{{white-space:pre-wrap;word-break:break-word;font-size:11px;margin:0}}
.scope{{margin-top:26px;padding:14px;background:#f6f7f9;border-left:3px solid #707780}}
@media(max-width:800px){{main{{margin:0;padding:20px}}.cards{{grid-template-columns:repeat(2,1fr)}}.toc ol{{columns:1}}.roadmap,.priority-list li{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}
@media print{{body{{background:#fff}}main{{border:0;margin:0;max-width:none;padding:0}}.cover{{break-after:page}}.toc,.cards article,.priority-list li,.roadmap article,tr{{break-inside:avoid}}h2,h3{{break-after:avoid-page}}#report-findings{{break-before:page}}}}
</style></head><body><main>
<header class="cover">{logo}<p class="organisation">{organisation}</p><h1>{report_title}</h1><div class="target">{target}</div>{client}{contact_html}{introduction}
<div class="meta"><span><strong>{_label(active, "Mode:")}</strong> {html.escape(_label(active, assessment.mode.title()))}</span><span><strong>{_label(active, "Generated:")}</strong> {generated}</span><span><strong>{_label(active, "Elapsed:")}</strong> {assessment.elapsed_ms} ms</span><span><strong>{_label(active, "Schema:")}</strong> {html.escape(assessment.schema_version)}</span></div></header>
{contents}{sections}<p class="scope">{html.escape(_SCOPE_ES if active.language == "es" else _SCOPE)}</p>
</main></body></html>"""
