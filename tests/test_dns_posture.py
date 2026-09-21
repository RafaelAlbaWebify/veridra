from __future__ import annotations

from veridra.core import Status
from veridra.dns_posture import (
    DnsLookupError,
    analyze_domain_posture,
    collect_domain_posture,
    discover_authoritative_domain,
)


def test_complete_domain_posture_passes() -> None:
    records = {
        ("example.com", "NS"): ["ns1.example.net.", "ns2.example.net."],
        ("example.com", "MX"): ["10 mail.example.com."],
        ("example.com", "TXT"): ["v=spf1 include:_spf.example.net -all"],
        ("_dmarc.example.com", "TXT"): ["v=DMARC1; p=reject; rua=mailto:dmarc@example.com"],
    }

    posture = collect_domain_posture(
        "Example.COM.",
        lookup=lambda name, record_type: records.get((name, record_type), []),
    )
    findings = {item.id: item for item in analyze_domain_posture(posture)}

    assert posture.domain == "example.com"
    assert all(item.status == Status.passed for item in findings.values())
    assert findings["email.dmarc"].evidence["policy"] == "reject"


def test_missing_and_monitoring_records_need_attention() -> None:
    records = {
        ("example.com", "NS"): ["ns1.example.net."],
        ("example.com", "MX"): [],
        ("example.com", "TXT"): [
            "v=spf1 -all",
            "v=spf1 include:mail.example.net -all",
        ],
        ("_dmarc.example.com", "TXT"): ["v=DMARC1; p=none"],
    }

    posture = collect_domain_posture(
        "example.com",
        lookup=lambda name, record_type: records.get((name, record_type), []),
    )
    findings = {item.id: item for item in analyze_domain_posture(posture)}

    assert findings["dns.nameservers"].status == Status.attention
    assert findings["email.mx"].status == Status.attention
    assert findings["email.spf"].status == Status.attention
    assert findings["email.dmarc"].status == Status.attention
    assert findings["email.dmarc"].evidence["policy"] == "none"


def test_lookup_failures_are_unavailable() -> None:
    def failing_lookup(name: str, record_type: str) -> list[str]:
        raise DnsLookupError(f"unavailable: {name} {record_type}")

    posture = collect_domain_posture("example.com", lookup=failing_lookup)
    findings = analyze_domain_posture(posture)

    assert all(item.status == Status.unavailable for item in findings)


def test_no_dmarc_record_is_attention() -> None:
    posture = collect_domain_posture(
        "example.com",
        lookup=lambda name, record_type: [],
    )
    findings = {item.id: item for item in analyze_domain_posture(posture)}

    assert findings["email.dmarc"].status == Status.attention
    assert findings["email.dmarc"].evidence["dmarc_records"] == []


def test_discover_authoritative_domain_walks_up_from_www_hostname() -> None:
    records = {
        ("example.ie", "NS"): ["ns1.example.net.", "ns2.example.net."],
    }

    domain = discover_authoritative_domain(
        "www.example.ie",
        lookup=lambda name, record_type: records.get((name, record_type), []),
    )

    assert domain == "example.ie"


def test_discover_authoritative_domain_respects_delegated_subdomain() -> None:
    records = {
        ("shop.example.ie", "NS"): ["ns1.shop-dns.example."],
        ("example.ie", "NS"): ["ns1.example.net.", "ns2.example.net."],
    }

    domain = discover_authoritative_domain(
        "app.shop.example.ie",
        lookup=lambda name, record_type: records.get((name, record_type), []),
    )

    assert domain == "shop.example.ie"


def test_domain_posture_evidence_records_queried_domain() -> None:
    records = {
        ("example.ie", "NS"): ["ns1.example.net.", "ns2.example.net."],
        ("example.ie", "MX"): ["10 mail.example.ie."],
        ("example.ie", "TXT"): ["v=spf1 -all"],
        ("_dmarc.example.ie", "TXT"): ["v=DMARC1; p=reject"],
    }

    posture = collect_domain_posture(
        "example.ie",
        lookup=lambda name, record_type: records.get((name, record_type), []),
    )
    findings = {item.id: item for item in analyze_domain_posture(posture)}

    assert findings["dns.nameservers"].evidence["domain"] == "example.ie"
    assert findings["email.mx"].evidence["domain"] == "example.ie"
    assert findings["email.spf"].evidence["domain"] == "example.ie"
    assert findings["email.dmarc"].evidence["domain"] == "example.ie"
