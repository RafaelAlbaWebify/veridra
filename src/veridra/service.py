from __future__ import annotations

from time import perf_counter
from urllib.parse import urlparse

from .accessibility import analyze_accessibility
from .collector import (
    PageEvidence,
    Requester,
    SiteEvidence,
    _request_once,
    collect_page,
    collect_site,
)
from .core import Assessment, Finding, Status, analyze_document
from .crawl import CrawlLimits, analyze_crawl, crawl_site
from .crawl_profiles import CrawlProfile, anonymous_crawl_profile
from .dns_posture import (
    RecordLookup,
    analyze_domain_posture,
    collect_domain_posture,
    live_lookup,
)
from .local_readiness import analyze_local_readiness
from .page_quality import analyze_page_quality
from .passive_security import analyze_passive_security


def _transport_findings(evidence: SiteEvidence) -> list[Finding]:
    homepage = evidence.homepage
    homepage_ok = 200 <= homepage.status_code < 400
    robots_available = evidence.robots is not None
    return [
        Finding(
            id="health.http-status",
            area="Website health",
            title="Homepage response",
            status=Status.passed if homepage_ok else Status.attention,
            severity="info" if homepage_ok else "high",
            summary=f"Homepage returned HTTP {homepage.status_code}.",
            recommendation=(
                None
                if homepage_ok
                else "Investigate the public homepage response and availability."
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
    findings.extend(
        analyze_document(
            evidence.homepage.body,
            evidence.homepage.headers,
            robots_text,
        )
    )
    findings.extend(analyze_local_readiness(evidence.homepage.body))

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
    findings.extend(analyze_crawl(crawl))
    findings.extend(analyze_page_quality(crawl))
    findings.extend(analyze_accessibility(crawl))
    findings.extend(analyze_passive_security(crawl))

    hostname = urlparse(evidence.homepage.final_url).hostname
    if hostname is not None:
        findings.extend(
            analyze_domain_posture(
                collect_domain_posture(hostname, lookup=dns_lookup)
            )
        )
    elapsed_ms = round((perf_counter() - started) * 1000)
    return Assessment.build(
        evidence.homepage.final_url,
        findings,
        mode="live",
        elapsed_ms=elapsed_ms,
    )
