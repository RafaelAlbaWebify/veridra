from __future__ import annotations

from datetime import UTC, datetime

from veridra.business_content_consistency import analyze_business_content_consistency
from veridra.collector import PageEvidence
from veridra.core import Finding, Status
from veridra.crawl import CrawlResult, CrawledPage


def _page(url: str, body: str) -> CrawledPage:
    return CrawledPage(
        PageEvidence(
            requested_url=url,
            final_url=url,
            status_code=200,
            headers={"content-type": "text/html"},
            body=body,
            redirect_chain=(),
            connected_ip="203.0.113.10",
            validated_ips=("203.0.113.10",),
        ),
        0,
    )


def _findings(*pages: CrawledPage) -> dict[str, Finding]:
    result = CrawlResult(
        pages=pages,
        skipped_urls=(),
        exhausted_page_limit=False,
        exhausted_byte_limit=False,
    )
    return {
        item.id: item
        for item in analyze_business_content_consistency(
            result,
            reference=datetime(2026, 9, 5, tzinfo=UTC),
        )
    }


def test_wordpress_sample_page_is_deterministic_placeholder_content() -> None:
    findings = _findings(
        _page(
            "https://example.ie/sample-page/",
            """<main><p>This is an example page. It’s different from a blog post because it will
            stay in one place and will show up in your site navigation.</p></main>""",
        )
    )
    finding = findings["content.placeholder-default"]
    assert finding.status == Status.attention
    assert finding.severity == "medium"
    assert finding.evidence["affected_pages"][0]["pattern"] == "wordpress_sample_page"


def test_literal_call_phone_number_placeholder_is_reported() -> None:
    finding = _findings(
        _page(
            "https://example.ie/",
            "<p>For an appointment please call phone number and our team will help.</p>",
        )
    )["content.placeholder-default"]
    assert finding.status == Status.attention
    assert finding.evidence["affected_pages"][0]["pattern"] == "literal_phone_placeholder"


def test_form_label_phone_number_is_not_placeholder_content() -> None:
    finding = _findings(
        _page(
            "https://example.ie/contact/",
            "<form><label>Phone number</label><input name='phone'></form>",
        )
    )["content.placeholder-default"]
    assert finding.status == Status.passed


def test_old_explicit_update_label_is_indicator_not_proof_of_error() -> None:
    finding = _findings(
        _page(
            "https://example.ie/advice/",
            "<p>Important patient information — Last Updated January 2024.</p>",
        )
    )["content.explicit-update-age"]
    assert finding.status == Status.attention
    assert finding.severity == "low"
    assert "not proof" in finding.summary.lower()
    assert finding.evidence["indicators"][0]["age_months_at_assessment"] == 32


def test_old_copyright_year_alone_is_not_staleness_finding() -> None:
    finding = _findings(
        _page("https://example.ie/", "<footer>Copyright © 2024 Example Dental</footer>")
    )["content.explicit-update-age"]
    assert finding.status == Status.passed
    assert finding.evidence["copyright_years_excluded"] is True


def test_cross_page_opening_hours_conflict_is_reported_with_both_urls() -> None:
    finding = _findings(
        _page(
            "https://example.ie/",
            "<p>Opening Hours Monday 9:00 am - 5:00 pm Tuesday 9:00 am - 5:00 pm</p>",
        ),
        _page(
            "https://example.ie/contact/",
            "<p>Opening Hours Monday 8:00 am - 6:00 pm Tuesday 9:00 am - 5:00 pm</p>",
        ),
    )["content.opening-hours-consistency"]
    assert finding.status == Status.attention
    assert finding.severity == "high"
    conflict = finding.evidence["conflicts"][0]
    assert conflict["first_url"] == "https://example.ie/"
    assert conflict["second_url"] == "https://example.ie/contact/"
    assert conflict["differences"] == [
        {"day": "monday", "first_value": "9:00am-5:00pm", "second_value": "8:00am-6:00pm"}
    ]
    assert finding.evidence["owner_confirmation_required_before_change"] is True


def test_matching_overlapping_hours_do_not_create_conflict() -> None:
    finding = _findings(
        _page("https://example.ie/", "<p>Monday 9am - 5pm Tuesday 9am - 5pm</p>"),
        _page("https://example.ie/contact/", "<p>Monday 9am - 5pm</p>"),
    )["content.opening-hours-consistency"]
    assert finding.status == Status.passed
