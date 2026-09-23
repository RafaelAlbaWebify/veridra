from __future__ import annotations

from veridra.collector import PageEvidence
from veridra.core import Finding, Status
from veridra.crawl import CrawledPage, CrawlResult
from veridra.local_readiness import analyze_local_readiness, analyze_local_readiness_crawl


def _by_id(document: str) -> dict[str, Finding]:
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


def test_missing_local_signals_do_not_duplicate_structured_parent_gap() -> None:
    findings = _by_id("<html><body><h1>General company website</h1></body></html>")

    assert all(item.area == "Local presence" for item in findings.values())
    assert findings["local.structured-business"].status == Status.attention
    for identifier in (
        "local.structured-name",
        "local.structured-url",
        "local.structured-phone",
        "local.structured-address",
        "local.structured-hours",
        "local.structured-same-as",
    ):
        assert findings[identifier].status == Status.unavailable
        assert findings[identifier].recommendation is None
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


def _page(url: str, body: str) -> CrawledPage:
    return CrawledPage(
        evidence=PageEvidence(
            requested_url=url,
            final_url=url,
            status_code=200,
            headers={"content-type": "text/html"},
            body=body,
            redirect_chain=(),
            connected_ip="203.0.113.10",
            validated_ips=("203.0.113.10",),
        ),
        depth=0,
    )


def test_crawl_local_presence_accepts_signal_on_non_homepage() -> None:
    crawl = CrawlResult(
        pages=(
            _page(
                "https://example.ie/",
                "<html><body><a href='/contact'>Contact</a></body></html>",
            ),
            _page(
                "https://example.ie/contact",
                "<html><body><address>1 Main Street, D02 X285</address>"
                "<a href='tel:+35312345678'>Call</a>"
                "<p>Opening hours Monday-Friday 09:00-17:00</p>"
                "<a href='https://maps.google.com/?q=Example'>Directions</a>"
                "</body></html>",
            ),
        ),
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )

    findings = {
        item.id: item
        for item in analyze_local_readiness_crawl(crawl)
    }

    assert findings["local.visible-phone"].status == Status.passed
    assert findings["local.visible-address"].status == Status.passed
    assert findings["local.visible-hours"].status == Status.passed
    assert findings["local.map-link"].status == Status.passed
    assert findings["local.visible-phone"].evidence["present_urls"] == [
        "https://example.ie/contact"
    ]


def test_visible_directions_text_counts_as_map_route() -> None:
    document = """
    <a href="/contact-us/">Click here for directions to our surgery</a>
    """

    findings = _by_id(document)

    assert findings["local.map-link"].status == Status.passed
    assert findings["local.location-route"].status == Status.passed


def test_visible_location_heading_counts_as_location_route() -> None:
    document = """
    <section>
      <h2>Our Location</h2>
      <p>1 Main Street, Dublin</p>
    </section>
    """

    findings = _by_id(document)

    assert findings["local.location-route"].status == Status.passed


def test_find_us_heading_counts_as_directions_route() -> None:
    document = """
    <section>
      <h2>Find Us</h2>
      <p>College Gate Clinic, Dublin</p>
    </section>
    """

    findings = _by_id(document)

    assert findings["local.location-route"].status == Status.passed
    assert findings["local.map-link"].status == Status.passed


def test_embedded_map_counts_as_map_route() -> None:
    document = """
    <iframe src="https://www.google.com/maps/embed?pb=example"></iframe>
    """

    findings = _by_id(document)

    assert findings["local.map-link"].status == Status.passed
