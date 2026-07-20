from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import dns.exception
import dns.resolver

from .core import Finding, Status


class DnsLookupError(RuntimeError):
    pass


RecordLookup = Callable[[str, str], list[str]]


@dataclass(frozen=True)
class DomainPosture:
    domain: str
    nameservers: tuple[str, ...] | None
    mail_exchangers: tuple[str, ...] | None
    txt_records: tuple[str, ...] | None
    dmarc_records: tuple[str, ...] | None


def live_lookup(name: str, record_type: str) -> list[str]:
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 2.0
    resolver.lifetime = 4.0
    try:
        answer = resolver.resolve(name, record_type, search=False)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
        raise DnsLookupError(f"DNS lookup failed for {name} {record_type}: {exc}") from exc
    return [str(item).strip().strip('"') for item in answer]


def _safe_lookup(lookup: RecordLookup, name: str, record_type: str) -> tuple[str, ...] | None:
    try:
        return tuple(sorted(set(lookup(name, record_type))))
    except DnsLookupError:
        return None


def collect_domain_posture(
    domain: str,
    *,
    lookup: RecordLookup = live_lookup,
) -> DomainPosture:
    normalized = domain.rstrip(".").lower()
    return DomainPosture(
        domain=normalized,
        nameservers=_safe_lookup(lookup, normalized, "NS"),
        mail_exchangers=_safe_lookup(lookup, normalized, "MX"),
        txt_records=_safe_lookup(lookup, normalized, "TXT"),
        dmarc_records=_safe_lookup(lookup, f"_dmarc.{normalized}", "TXT"),
    )


def _unavailable(identifier: str, title: str, recommendation: str) -> Finding:
    return Finding(
        id=identifier,
        area="Trust signals",
        title=title,
        status=Status.unavailable,
        severity="low",
        summary=f"{title} could not be verified within the bounded DNS lookup.",
        recommendation=recommendation,
    )


def analyze_domain_posture(posture: DomainPosture) -> list[Finding]:
    nameservers = posture.nameservers
    if nameservers is None:
        nameserver_finding = _unavailable(
            "dns.nameservers",
            "Authoritative nameservers",
            "Retry later or verify delegation with the domain operator.",
        )
    else:
        redundant = len(nameservers) >= 2
        nameserver_finding = Finding(
            id="dns.nameservers",
            area="Trust signals",
            title="Authoritative nameservers",
            status=Status.passed if redundant else Status.attention,
            severity="info" if redundant else "medium",
            summary=f"{len(nameservers)} authoritative nameserver records were found.",
            recommendation=(
                None
                if redundant
                else "Use at least two authoritative nameservers on independent infrastructure."
            ),
            evidence={"nameservers": list(nameservers)},
        )

    mail_exchangers = posture.mail_exchangers
    if mail_exchangers is None:
        mx_finding = _unavailable(
            "email.mx",
            "Mail exchanger records",
            "Retry later or verify the domain MX records.",
        )
    else:
        present = bool(mail_exchangers)
        mx_finding = Finding(
            id="email.mx",
            area="Trust signals",
            title="Mail exchanger records",
            status=Status.passed if present else Status.attention,
            severity="info" if present else "medium",
            summary=(
                "Public mail exchanger records are present."
                if present
                else "No public mail exchanger records were returned."
            ),
            recommendation=(
                None
                if present
                else "Publish MX records when the domain should receive email, or document that it is intentionally non-mail-enabled."
            ),
            evidence={"mail_exchangers": list(mail_exchangers)},
        )

    txt_records = posture.txt_records
    if txt_records is None:
        spf_finding = _unavailable(
            "email.spf",
            "SPF policy",
            "Retry later or verify the domain TXT records.",
        )
    else:
        spf_records = tuple(record for record in txt_records if record.lower().startswith("v=spf1"))
        valid = len(spf_records) == 1
        spf_finding = Finding(
            id="email.spf",
            area="Trust signals",
            title="SPF policy",
            status=Status.passed if valid else Status.attention,
            severity="info" if valid else "medium",
            summary=(
                "Exactly one SPF policy was found."
                if valid
                else f"Expected exactly one SPF policy; found {len(spf_records)}."
            ),
            recommendation=(
                None
                if valid
                else "Publish exactly one SPF record and consolidate all permitted senders into it."
            ),
            evidence={"spf_records": list(spf_records)},
        )

    dmarc_records = posture.dmarc_records
    if dmarc_records is None:
        dmarc_finding = _unavailable(
            "email.dmarc",
            "DMARC policy",
            "Retry later or verify the _dmarc TXT record.",
        )
    else:
        candidates = tuple(
            record for record in dmarc_records if record.lower().startswith("v=dmarc1")
        )
        record = candidates[0] if len(candidates) == 1 else ""
        tags = {
            key.strip().lower(): value.strip().lower()
            for part in record.split(";")
            if "=" in part
            for key, value in [part.split("=", 1)]
        }
        policy = tags.get("p")
        valid = len(candidates) == 1 and policy is not None
        enforcing = policy in {"quarantine", "reject"}
        dmarc_finding = Finding(
            id="email.dmarc",
            area="Trust signals",
            title="DMARC policy",
            status=Status.passed if valid and enforcing else Status.attention,
            severity="info" if valid and enforcing else "medium",
            summary=(
                f"A DMARC policy with p={policy} is published."
                if valid
                else f"Expected one valid DMARC policy; found {len(candidates)}."
            ),
            recommendation=(
                None
                if valid and enforcing
                else "Publish one valid DMARC record and progress from monitoring to quarantine or reject when ready."
            ),
            evidence={"dmarc_records": list(candidates), "policy": policy},
        )

    return [nameserver_finding, mx_finding, spf_finding, dmarc_finding]
