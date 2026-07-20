from __future__ import annotations

from .collector import Requester, SiteEvidence, _request_once, collect_site
from .core import Assessment, Finding, Status, analyze_document


def _transport_findings(evidence: SiteEvidence) -> list[Finding]:
    homepage = evidence.homepage
    return [
        Finding(
            id="health.http-status",
            area="Website health",
            title="Homepage response",
            status=Status.passed if 200 <= homepage.status_code < 400 else Status.attention,
            severity="info" if 200 <= homepage.status_code < 400 else "high",
            summary=f"Homepage returned HTTP {homepage.status_code}.",
            recommendation=None
            if 200 <= homepage.status_code < 400
            else "Investigate the public homepage response and availability.",
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
            status=Status.passed if evidence.robots is not None else Status.unavailable,
            severity="info" if evidence.robots is not None else "low",
            summary="robots.txt was collected."
            if evidence.robots is not None
            else "robots.txt could not be collected within the bounded request scope.",
            recommendation=None
            if evidence.robots is not None
            else "Confirm whether a public robots.txt file should be available.",
        ),
    ]


def assess_url(raw_url: str, *, requester: Requester = _request_once) -> Assessment:
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
    return Assessment.build(evidence.homepage.final_url, findings)
