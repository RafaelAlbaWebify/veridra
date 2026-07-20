from __future__ import annotations

from time import perf_counter

from .collector import Requester, SiteEvidence, _request_once, collect_site
from .core import Assessment, Finding, Status, analyze_document


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
            status=(
                Status.passed if robots_available else Status.unavailable
            ),
            severity="info" if robots_available else "low",
            summary=(
                "robots.txt was collected."
                if robots_available
                else (
                    "robots.txt could not be collected within the bounded "
                    "request scope."
                )
            ),
            recommendation=(
                None
                if robots_available
                else "Confirm whether a public robots.txt file should be available."
            ),
        ),
    ]


def assess_url(
    raw_url: str,
    *,
    requester: Requester = _request_once,
) -> Assessment:
    started = perf_counter()
    evidence = collect_site(raw_url, requester=requester)
    robots_text = evidence.robots.body if evidence.robots is not None else ""
    findings = _transport_findings(evidence)
    findings.extend(
        analyze_document(
            evidence.homepage.body,
            evidence.homepage.headers,
            robots_text,
        )
    )
    elapsed_ms = round((perf_counter() - started) * 1000)
    return Assessment.build(
        evidence.homepage.final_url,
        findings,
        mode="live",
        elapsed_ms=elapsed_ms,
    )
