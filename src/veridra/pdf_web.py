from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from .app import _resolve_assessment, _resolve_profile
from .pdf_reports import PdfRenderError, render_pdf
from .reports import render_report

router = APIRouter()


@router.get("/report.pdf")
def report_pdf(
    url: str | None = Query(default=None, min_length=1, max_length=2048),
    demo: bool = False,
    profile: str | None = Query(default=None, max_length=24),
) -> Response:
    assessment = _resolve_assessment(url, demo)
    report_profile = _resolve_profile(profile)
    report_html = render_report(assessment, report_profile)
    try:
        document = render_pdf(report_html, target=str(assessment.target))
    except PdfRenderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=document.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
