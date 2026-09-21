from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .core import Finding


class ServiceClass(StrEnum):
    activation = "activation"
    monthly_allowance = "monthly allowance"
    separate_quote = "separate quote"
    monitor_only = "monitor-only"
    informational = "informational"
    discard = "discard"


@dataclass(frozen=True, slots=True)
class FindingValue:
    owner_understandable: bool
    commercially_relevant: bool
    webify_remediable: bool
    service_class: ServiceClass
    rationale: str


_HIGH_VALUE_IDS = {
    "content.placeholder-default",
    "content.opening-hours-consistency",
    "crawl.broken-internal-links",
    "crawl.http-status",
    "local.visible-phone",
    "local.visible-address",
    "local.visible-hours",
    "local.map-link",
    "local.location-route",
}

_ACTIVATION_IDS = {
    "crawl.canonical",
    "crawl.description",
    "crawl.duplicate-titles",
    "crawl.duplicate-descriptions",
    "crawl.h1",
    "crawl.image-alt",
    "local.structured-business",
    "search.sitemap",
    "ai.structured-data",
    "ai.open-graph-title",
    "ai.open-graph-description",
    "trust.about",
    "trust.contact",
    "trust.privacy",
    "trust.terms",
}

_MONITOR_ONLY_IDS = {
    "content.explicit-update-age",
    "security.server-disclosure",
    "security.target-blank-isolation",
    "security.permissions",
    "security.referrer",
    "security.nosniff",
    "accessibility.heading-order",
    "accessibility.duplicate-ids",
    "accessibility.document-language",
}

_SECURITY_SEPARATE_QUOTE_IDS = {
    "security.cookie-flags",
    "security.cross-origin-forms",
    "security.insecure-form-actions",
    "security.insecure-resources",
    "security.csp-unsafe-directives",
}

_EMAIL_POSTURE_IDS = {
    "email.mx",
    "email.spf",
    "email.dmarc",
    "dns.nameservers",
}


def classify_finding_value(finding: Finding) -> FindingValue:
    identifier = finding.id

    if identifier in _HIGH_VALUE_IDS:
        return FindingValue(
            owner_understandable=True,
            commercially_relevant=True,
            webify_remediable=True,
            service_class=ServiceClass.activation,
            rationale="Direct customer-facing, conversion, trust, or public-fact issue.",
        )

    if identifier in _ACTIVATION_IDS:
        return FindingValue(
            owner_understandable=True,
            commercially_relevant=True,
            webify_remediable=True,
            service_class=ServiceClass.activation,
            rationale="Credible website quality/discoverability improvement suitable for setup.",
        )

    if identifier in _SECURITY_SEPARATE_QUOTE_IDS:
        return FindingValue(
            owner_understandable=False,
            commercially_relevant=True,
            webify_remediable=True,
            service_class=ServiceClass.separate_quote,
            rationale=(
                "Potentially meaningful public security posture issue, but remediation "
                "requires stack/context review rather than routine monthly work."
            ),
        )

    if identifier in _EMAIL_POSTURE_IDS:
        return FindingValue(
            owner_understandable=True,
            commercially_relevant=True,
            webify_remediable=True,
            service_class=ServiceClass.separate_quote,
            rationale=(
                "Email/domain trust configuration can matter commercially but requires "
                "domain-owner/provider access and explicit authorization."
            ),
        )

    if identifier in _MONITOR_ONLY_IDS:
        return FindingValue(
            owner_understandable=True,
            commercially_relevant=False,
            webify_remediable=True,
            service_class=ServiceClass.monitor_only,
            rationale=(
                "Technically useful hygiene signal, but weak as a standalone commercial "
                "reason to sell or prioritize work."
            ),
        )

    if identifier.startswith("accessibility."):
        return FindingValue(
            owner_understandable=True,
            commercially_relevant=finding.severity in {"high", "critical"},
            webify_remediable=True,
            service_class=(
                ServiceClass.activation
                if finding.severity in {"high", "critical"}
                else ServiceClass.monthly_allowance
            ),
            rationale=(
                "Accessibility issue is actionable; higher-severity interaction/form "
                "problems carry stronger customer impact than structural hygiene."
            ),
        )

    if identifier in {"security.hsts", "security.csp", "security.frames"}:
        return FindingValue(
            owner_understandable=False,
            commercially_relevant=False,
            webify_remediable=True,
            service_class=ServiceClass.monitor_only,
            rationale=(
                "Valid hardening signal but not a strong standalone SMB Presence Care "
                "value proposition without a concrete exploit/customer-impact condition."
            ),
        )

    if identifier.startswith("crawl.") or identifier.startswith("search."):
        return FindingValue(
            owner_understandable=True,
            commercially_relevant=True,
            webify_remediable=True,
            service_class=ServiceClass.activation,
            rationale="Observable website/search quality issue with a bounded remediation path.",
        )

    if identifier.startswith("local.") or identifier.startswith("trust."):
        return FindingValue(
            owner_understandable=True,
            commercially_relevant=True,
            webify_remediable=True,
            service_class=ServiceClass.activation,
            rationale="Public trust/local-presence gap relevant to an SMB customer journey.",
        )

    if identifier.startswith("ai."):
        return FindingValue(
            owner_understandable=True,
            commercially_relevant=False,
            webify_remediable=True,
            service_class=ServiceClass.informational,
            rationale=(
                "Readiness signal only; VERIDRA must not imply proven AI visibility or "
                "customer acquisition impact."
            ),
        )

    return FindingValue(
        owner_understandable=True,
        commercially_relevant=False,
        webify_remediable=False,
        service_class=ServiceClass.informational,
        rationale="No stronger Presence Care service classification is currently justified.",
    )
