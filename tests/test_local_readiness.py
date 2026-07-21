from __future__ import annotations

from veridra.core import Status
from veridra.local_readiness import analyze_local_readiness


def _by_id(document: str):
    return {item.id: item for item in analyze_local_readiness(document)}


def test_complete_local_business_signals_pass() -> None:
    document = """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "ProfessionalService",
        "name": "Example Services",
        "url": "https://example.com",
        "telephone": "+34 986 123 456",
        "address": {
          "@type": "PostalAddress",
          "streetAddress": "1 Main Street",
          "postalCode": "36201"
        },
        "openingHours": "Mo-Fr 09:00-18:00",
        "sameAs": ["https://www.linkedin.com/company/example"]
      }
      </script>
    </head><body>
      <address>1 Main Street, 36201 Vigo</address>
      <a href="tel:+34986123456">+34 986 123 456</a>
      <p>Opening hours Monday–Friday 09:00–18:00</p>
      <a href="https://maps.google.com/?q=Example">Directions</a>
      <a href="/locations">Our locations</a>
    </body></html>
    """

    findings = _by_id(document)

    assert len(findings) == 12
    assert all(item.status == Status.passed for item in findings.values())
    assert findings["local.structured-business"].evidence["local_business_nodes"] == 1
    assert "professionalservice" in findings["local.structured-business"].evidence[
        "detected_types"
    ]


def test_missing_local_signals_are_independent_attention_findings() -> None:
    findings = _by_id("<html><body><h1>General company website</h1></body></html>")

    assert all(item.area == "Local presence" for item in findings.values())
    assert findings["local.structured-business"].status == Status.attention
    assert findings["local.visible-phone"].status == Status.attention
    assert findings["local.visible-address"].status == Status.attention
    assert findings["local.visible-hours"].status == Status.attention
    assert findings["local.map-link"].status == Status.attention
    assert findings["local.location-route"].status == Status.attention


def test_graph_and_type_arrays_are_supported() -> None:
    document = """
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@graph": [
          {"@type": "WebSite", "name": "Site"},
          {
            "@type": ["Organization", "LocalBusiness"],
            "name": "Shop",
            "url": "https://example.com",
            "telephone": "+353 1 234 5678",
            "address": {"postalCode": "D02 X285"},
            "openingHoursSpecification": [{"dayOfWeek": "Monday"}],
            "sameAs": "https://example.social/shop"
          }
        ]
      }
    </script>
    """

    findings = _by_id(document)

    for identifier in (
        "local.structured-business",
        "local.structured-name",
        "local.structured-url",
        "local.structured-phone",
        "local.structured-address",
        "local.structured-hours",
        "local.structured-same-as",
    ):
        assert findings[identifier].status == Status.passed


def test_invalid_json_ld_is_reported_without_crashing() -> None:
    document = """
    <script type="application/ld+json">{not valid json</script>
    <a href="tel:+34986123456">Call us</a>
    """

    findings = _by_id(document)

    structured = findings["local.structured-business"]
    assert structured.status == Status.attention
    assert structured.evidence["invalid_json_ld_blocks"] == 1
    assert findings["local.visible-phone"].status == Status.passed


def test_map_and_location_routes_are_detected_from_links() -> None:
    document = """
    <a href="https://www.openstreetmap.org/directions?to=1,2">Route</a>
    <a href="/where-we-are">Where we are</a>
    """

    findings = _by_id(document)

    assert findings["local.map-link"].status == Status.passed
    assert findings["local.location-route"].status == Status.passed
