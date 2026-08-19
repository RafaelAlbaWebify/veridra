from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape, unescape

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

_MAX_HTML_BYTES = 5_000_000
_MAX_PDF_BYTES = 20_000_000
_RENDER_TIMEOUT_MS = 20_000
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_REPORT_TITLE_SUFFIX = " assessment report"


class PdfRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class PdfDocument:
    content: bytes
    filename: str


def report_brand_from_html(report_html: str) -> str:
    match = _TITLE.search(report_html)
    if match is None:
        return "Veridra"
    title = unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    if title.lower().endswith(_REPORT_TITLE_SUFFIX):
        title = title[: -len(_REPORT_TITLE_SUFFIX)].strip()
    return title[:120] or "Veridra"


def safe_pdf_filename(target: str, *, brand: str = "Veridra") -> str:
    cleaned_brand = re.sub(r"[^a-zA-Z0-9._-]+", "-", brand).strip("-.")
    cleaned_target = re.sub(r"[^a-zA-Z0-9._-]+", "-", target).strip("-.")
    prefix = cleaned_brand[:60] or "report"
    target_stem = cleaned_target[:60] or "website"
    return f"{prefix}-{target_stem}-assessment.pdf"


def render_pdf(html: str, *, target: str) -> PdfDocument:
    encoded = html.encode("utf-8")
    if len(encoded) > _MAX_HTML_BYTES:
        raise PdfRenderError("Report HTML exceeded the bounded PDF input size.")

    brand = report_brand_from_html(html)
    footer_brand = escape(brand)

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
                        f"<span>{footer_brand} website assessment</span>"
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
    return PdfDocument(
        content=content,
        filename=safe_pdf_filename(target, brand=brand),
    )
