from __future__ import annotations

import json
from time import perf_counter
from urllib.parse import urlparse

from .accessibility import analyze_accessibility
from .business_content_consistency import analyze_business_content_consistency
from .collector import (
    PageEvidence,
    Requester,
    SiteEvidence,
    _request_once,
    collect_page,
    collect_site,
)
from .commercial_crawl_findings import analyze_commercial_crawl_findings
from .core import Assessment, Finding, Status, analyze_document
from .crawl import CrawlLimits, analyze_crawl, crawl_site
from .crawl_profiles import CrawlProfile, anonymous_crawl_profile
from .dns_posture import (
    RecordLookup,
    analyze_domain_posture,
    collect_domain_posture,
    discover_authoritative_domain,
    discover_public_email_domain,
    live_lookup,
)
from .local_readiness import analyze_local_readiness_crawl
from .observations import ObservedAssessment, observation_records, page_observations
from .page_quality import analyze_page_quality
from .passive_security import analyze_passive_security
from .version import __version__


def _transport_findings(evidence: SiteEvidence) -> list[Finding]:
    homepage = evidence.homepage
    homepage_ok = homepage.status_code == 200
    homepage_intermediate = 200 <= homepage.status_code < 400 and not homepage_ok
    robots_available = evidence.robots is not None
    return [
        Finding(
            id="health.http-status",
            area="Website health",
            title="Homepage response",
            status=(
                Status.passed
                if homepage_ok
                else (Status.unavailable if homepage_intermediate else Status.attention)
            ),
            severity=(
                "info"
                if homepage_ok
                else ("low" if homepage_intermediate else "high")
            ),
            summary=(
                f"Homepage returned HTTP {homepage.status_code}."
                if homepage_ok or not homepage_intermediate
                else (
                    f"Homepage returned HTTP {homepage.status_code}; the response was "
                    "not treated as representative page content."
                )
            ),
            recommendation=(
                None
                if homepage_ok
                else (
                    "Retry or verify the public homepage response before drawing "
                    "content-level conclusions."
                    if homepage_intermediate
                    else "Investigate the public homepage response and availability."
                )
            ),
            evidence={
                "requested_url": homepage.requested_url,
                "final_url": homepage.final_url,
                "connected_ip": homepage.connected_ip,
                "validated_ips": list(homepage.validated_ips),
                "redirect_chain": list(homepage.redirect_chain),
            },
        ),
        Finding(
            id="search.robots-availability",
            area="Search visibility",
            title="robots.txt availability",
            status=(Status.passed if robots_available else Status.unavailable),
            severity="info" if robots_available else "low",
            summary=(
                "robots.txt was collected."
                if robots_available
                else "robots.txt could not be collected within the bounded request scope."
            ),
            recommendation=(
                None
                if robots_available
                else "Confirm whether a public robots.txt file should be available."
            ),
        ),
    ]


def _crawl_profile_finding(profile: CrawlProfile) -> Finding:
    return Finding(
        id="crawl.effective-limits",
        area="Website health",
        title="Effective crawl limits",
        status=Status.passed,
        severity="info",
        summary=(
            f"The {profile.name.value} crawl profile was applied with explicit "
            "server-side limits."
        ),
        evidence=profile.evidence(),
    )


def _effective_limits_evidence(limits: CrawlLimits) -> dict[str, int | float]:
    return {
        "max_pages": limits.max_pages,
        "max_depth": limits.max_depth,
        "max_total_bytes": limits.max_total_bytes,
        "per_page_bytes": limits.per_page_bytes,
        "timeout": limits.timeout,
        "max_sitemaps": limits.max_sitemaps,
        "max_sitemap_urls": limits.max_sitemap_urls,
    }


def _aligned_crawl_findings(
    crawl_findings: list[Finding],
    security_findings: list[Finding],
) -> list[Finding]:
    active_resource = next(
        (item for item in security_findings if item.id == "security.insecure-resources"),
        None,
    )
    if active_resource is None:
        return crawl_findings

    affected_pages = active_resource.evidence.get("affected_pages", [])
    affected_urls = [
        str(item.get("url", ""))
        for item in affected_pages
        if isinstance(item, dict) and item.get("url")
    ]
    aligned: list[Finding] = []
    for finding in crawl_findings:
        if finding.id != "crawl.mixed-content":
            aligned.append(finding)
            continue
        attention = active_resource.status == Status.attention
        evidence = dict(finding.evidence)
        evidence["affected_urls"] = sorted(set(affected_urls))
        evidence["classification"] = (
            "active HTTP subresources only; ordinary anchors and metadata references excluded"
        )
        aligned.append(
            Finding(
                id=finding.id,
                area=finding.area,
                title="Multi-page active HTTP subresources",
                status=Status.attention if attention else Status.passed,
                severity="high" if attention else "info",
                summary=(
                    f"{len(set(affected_urls))} crawled HTML pages reference active HTTP "
                    "subresources."
                    if attention
                    else "No active HTTP subresources were observed in the bounded crawl."
                ),
                recommendation=(
                    "Move active HTTP subresources to validated HTTPS endpoints where supported."
                    if attention
                    else None
                ),
                evidence=evidence,
            )
        )
    return aligned




_STATUS_RANK = {
    Status.attention: 3,
    Status.unavailable: 2,
    Status.passed: 1,
}

_SEVERITY_RANK = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}


def _finding_preference(finding: Finding) -> tuple[int, int, int]:
    return (
        _STATUS_RANK.get(finding.status, 0),
        _SEVERITY_RANK.get(finding.severity.casefold(), 0),
        len(json.dumps(finding.evidence, sort_keys=True, default=str)),
    )


def _deduplicate_finding_ids(findings: list[Finding]) -> list[Finding]:
    """Keep one deterministic, strongest/richest representation per semantic finding ID."""
    selected: dict[str, Finding] = {}
    order: list[str] = []
    for finding in findings:
        current = selected.get(finding.id)
        if current is None:
            selected[finding.id] = finding
            order.append(finding.id)
            continue
        if _finding_preference(finding) > _finding_preference(current):
            selected[finding.id] = finding
    return [selected[identifier] for identifier in order]


_REDUNDANT_LIVE_FINDINGS: dict[str, str] = {
    "health.language": "accessibility.document-language",
    "health.title": "crawl.title",
    "ai.structured-data": "local.structured-business",
    "health.viewport": "accessibility.viewport",
    "search.canonical": "crawl.canonical",
    "search.description": "crawl.description",
    "trust.heading": "crawl.h1",
    "accessibility.image-alt": "crawl.image-alt",
    "crawl.mixed-content": "security.insecure-resources",
    "security.mixed-content": "security.insecure-resources",
}


def _suppress_redundant_live_findings(findings: list[Finding]) -> list[Finding]:
    identifiers = {finding.id for finding in findings}
    return [
        finding
        for finding in findings
        if not (
            finding.id in _REDUNDANT_LIVE_FINDINGS
            and _REDUNDANT_LIVE_FINDINGS[finding.id] in identifiers
        )
    ]


def assess_url(
    raw_url: str,
    *,
    requester: Requester = _request_once,
    dns_lookup: RecordLookup = live_lookup,
    crawl_limits: CrawlLimits | None = None,
    crawl_profile: CrawlProfile | None = None,
) -> Assessment:
    started = perf_counter()
    active_profile = crawl_profile or anonymous_crawl_profile()
    if crawl_limits is not None and crawl_profile is not None:
        raise ValueError("Use crawl_limits or crawl_profile, not both.")
    effective_limits = crawl_limits or active_profile.limits
    evidence = collect_site(raw_url, requester=requester)
    robots_text = evidence.robots.body if evidence.robots is not None else ""
    findings = _transport_findings(evidence)
    findings.append(_crawl_profile_finding(active_profile))
    if evidence.homepage.status_code == 200:
        findings.extend(
            analyze_document(
                evidence.homepage.body,
                evidence.homepage.headers,
                robots_text,
            )
        )
    def collect_crawl_page(
        url: str,
        *,
        timeout: float,
        max_bytes: int,
    ) -> PageEvidence:
        return collect_page(
            url,
            timeout=timeout,
            max_bytes=max_bytes,
            requester=requester,
        )

    crawl = crawl_site(
        evidence.homepage.final_url,
        limits=effective_limits,
        collector=collect_crawl_page,
        robots_text=robots_text,
    )
    findings.extend(analyze_local_readiness_crawl(crawl))
    security_findings = analyze_passive_security(crawl)
    findings.extend(_aligned_crawl_findings(analyze_crawl(crawl), security_findings))
    findings.extend(analyze_commercial_crawl_findings(crawl))
    findings.extend(analyze_business_content_consistency(crawl))
    findings.extend(analyze_page_quality(crawl))
    findings.extend(analyze_accessibility(crawl))
    findings.extend(security_findings)

    hostname = urlparse(evidence.homepage.final_url).hostname
    if hostname is not None:
        posture_domain = discover_authoritative_domain(hostname, lookup=dns_lookup)
        public_email_domain = discover_public_email_domain(
            hostname,
            [page.evidence.body for page in crawl.pages],
        )
        findings.extend(
            analyze_domain_posture(
                collect_domain_posture(
                    posture_domain,
                    email_domain=public_email_domain,
                    lookup=dns_lookup,
                )
            )
        )
    findings = _suppress_redundant_live_findings(findings)
    findings = _deduplicate_finding_ids(findings)
    elapsed_ms = round((perf_counter() - started) * 1000)
    assessment = Assessment.build(
        evidence.homepage.final_url,
        findings,
        mode="live",
        elapsed_ms=elapsed_ms,
    )
    pages = page_observations(crawl)
    return ObservedAssessment.from_assessment(
        assessment,
        pages=pages,
        observations=observation_records(pages),
        collector_version=__version__,
        crawl_profile=active_profile.name.value,
        effective_crawl_limits=_effective_limits_evidence(effective_limits),
    )
