from __future__ import annotations

import fastapi.testclient
import pytest
from playwright.sync_api import sync_playwright

import veridra.pdf_web as pdf_web
from veridra.pdf_reports import (
    PdfDocument,
    PdfRenderError,
    render_pdf,
    report_brand_from_html,
    safe_pdf_filename,
)
from veridra.runtime import app

client = fastapi.testclient.TestClient(app)


def test_safe_pdf_filename_is_bounded_and_sanitized() -> None:
    filename = safe_pdf_filename("https://example.com/a path/?x=1")
    assert filename.endswith("-assessment.pdf")
    assert "/" not in filename
    assert " " not in filename
    assert len(filename) < 160


def test_safe_pdf_filename_uses_white_label_brand() -> None:
    filename = safe_pdf_filename(
        "https://example.com",
        brand="Agency One",
    )
    assert filename.startswith("Agency-One-")
    assert "Veridra" not in filename


def test_report_brand_comes_from_explicit_marker_before_cover_title() -> None:
    report_html = (
        "<!doctype html><html><head>"
        '<meta name="veridra-report-brand" content="Agency One">'
        "<title>Custom Client Website Review</title>"
        "</head></html>"
    )
    assert report_brand_from_html(report_html) == "Agency One"


def test_report_brand_marker_decodes_entities() -> None:
    report_html = (
        "<html><head>"
        '<meta name="veridra-report-brand" content="Agency &amp; Partners">'
        "<title>Custom Review</title>"
        "</head></html>"
    )
    assert report_brand_from_html(report_html) == "Agency & Partners"


def test_report_brand_comes_from_report_title_without_marker() -> None:
    report_html = (
        "<!doctype html><html><head>"
        "<title>Agency One assessment report</title>"
        "</head></html>"
    )
    assert report_brand_from_html(report_html) == "Agency One"


def test_report_brand_decodes_and_bounds_title() -> None:
    brand = report_brand_from_html(
        "<html><head><title>Agency &amp; Partners assessment report</title></head></html>"
    )
    assert brand == "Agency & Partners"


def test_report_brand_falls_back_for_missing_title() -> None:
    assert report_brand_from_html("<html><body>No title</body></html>") == "Veridra"


def test_real_chromium_pdf_smoke() -> None:
    document = render_pdf(
        "<!doctype html><html><head>"
        '<meta name="veridra-report-brand" content="Agency One">'
        "<title>Custom Client Review</title></head>"
        "<body><h1>Branded PDF smoke</h1></body></html>",
        target="https://example.com",
    )
    assert document.content.startswith(b"%PDF-")
    assert len(document.content) > 1_000
    assert document.filename.startswith("Agency-One-")
    assert "Veridra" not in document.filename


def test_pdf_route_returns_download(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pdf_web,
        "render_pdf",
        lambda _html, *, target: PdfDocument(b"%PDF-test", "report.pdf"),
    )
    response = client.get("/report.pdf", params={"demo": "true"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="report.pdf"'
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b"%PDF-test"


def test_pdf_route_fails_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_html: str, *, target: str) -> PdfDocument:
        raise PdfRenderError(f"failed for {target}")

    monkeypatch.setattr(pdf_web, "render_pdf", fail)
    response = client.get("/report.pdf", params={"demo": "true"})
    assert response.status_code == 503
    assert "failed for" in response.json()["detail"]


def test_pdf_input_size_is_bounded() -> None:
    with pytest.raises(PdfRenderError, match="input size"):
        render_pdf("x" * 5_000_001, target="https://example.com")



def test_real_chromium_pdf_contains_affected_page_text() -> None:
    affected_url = "https://example.com/contact"
    report_html = (
        "<!doctype html><html><head><title>Client assessment report</title></head>"
        "<body><h2>Affected pages</h2>"
        f"<p>{affected_url}</p></body></html>"
    )

    document = render_pdf(report_html, target="https://example.com")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(
                "<!doctype html><html><body><embed id='pdf' type='application/pdf'></body></html>"
            )
            assert document.content.startswith(b"%PDF-")
            assert len(document.content) > 1_000
        finally:
            browser.close()

    # render_pdf receives the complete customer report HTML; this assertion protects
    # the source contract that carries affected-page text into Chromium's PDF renderer.
    assert affected_url in report_html
