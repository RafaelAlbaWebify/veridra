from __future__ import annotations

import fastapi.testclient
import pytest

import veridra.pdf_web as pdf_web
from veridra.pdf_reports import PdfDocument, PdfRenderError, render_pdf, safe_pdf_filename
from veridra.runtime import app

client = fastapi.testclient.TestClient(app)


def test_safe_pdf_filename_is_bounded_and_sanitized() -> None:
    filename = safe_pdf_filename("https://example.com/a path/?x=1")
    assert filename.endswith("-assessment.pdf")
    assert "/" not in filename
    assert " " not in filename
    assert len(filename) < 160


def test_real_chromium_pdf_smoke() -> None:
    document = render_pdf(
        "<!doctype html><html><body><h1>Veridra PDF smoke</h1></body></html>",
        target="https://example.com",
    )
    assert document.content.startswith(b"%PDF-")
    assert len(document.content) > 1_000


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
