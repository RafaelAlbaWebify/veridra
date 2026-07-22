from __future__ import annotations

import re
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

_MAX_HTML_BYTES = 5_000_000
_MAX_PDF_BYTES = 20_000_000
_RENDER_TIMEOUT_MS = 20_000


class PdfRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class PdfDocument:
    content: bytes
    filename: str


def safe_pdf_filename(target: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", target).strip("-.")
    stem = cleaned[:120] or "website"
    return f"veridra-{stem}-assessment.pdf"


def render_pdf(html: str, *, target: str) -> PdfDocument:
    encoded = html.encode("utf-8")
    if len(encoded) > _MAX_HTML_BYTES:
        raise PdfRenderError("Report HTML exceeded the bounded PDF input size.")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(_RENDER_TIMEOUT_MS)
                page.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(("about:", "data:"))
                        else route.abort()
                    ),
                )
                page.set_content(html, wait_until="domcontentloaded", timeout=_RENDER_TIMEOUT_MS)
                content = page.pdf(
                    format="A4",
                    print_background=True,
                    display_header_footer=True,
                    margin={"top": "18mm", "right": "12mm", "bottom": "18mm", "left": "12mm"},
                    header_template="<div></div>",
                    footer_template=(
                        "<div style='font-size:8px;width:100%;padding:0 12mm;"
                        "color:#667085;display:flex;justify-content:space-between'>"
                        "<span>Veridra website assessment</span>"
                        "<span><span class='pageNumber'></span> / "
                        "<span class='totalPages'></span></span></div>"
                    ),
                    prefer_css_page_size=True,
                )
            finally:
                browser.close()
    except (PlaywrightError, PlaywrightTimeoutError, OSError) as exc:
        raise PdfRenderError("The PDF renderer could not complete safely.") from exc

    if not content.startswith(b"%PDF-"):
        raise PdfRenderError("The PDF renderer returned an invalid document.")
    if len(content) > _MAX_PDF_BYTES:
        raise PdfRenderError("Generated PDF exceeded the bounded output size.")
    return PdfDocument(content=content, filename=safe_pdf_filename(target))
