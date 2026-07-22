from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import HTMLResponse

from .collector import CollectionError
from .core import Assessment, UnsafeTargetError
from .crawl_profiles import CrawlProfile, resolve_crawl_profile
from .exports import build_evidence_package
from .pdf_reports import PdfRenderError, render_pdf
from .profile_store import ProfileStore, ProfileStoreError
from .project_store import ClientProject, ProjectStore, ProjectStoreError
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile
from .reports import render_report
from .service import assess_url

router = APIRouter(prefix="/crawl", tags=["crawl profiles"])


def _profile(
    crawl_profile: str,
    max_pages: int | None,
    max_depth: int | None,
) -> CrawlProfile:
    try:
        return resolve_crawl_profile(
            crawl_profile,
            max_pages=max_pages,
            max_depth=max_depth,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _report_profile(profile_id: str | None) -> ReportProfile:
    if profile_id is None:
        return DEFAULT_REPORT_PROFILE
    try:
        return ProfileStore().load(profile_id)
    except ProfileStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _project(entry_id: str) -> ClientProject:
    try:
        return ProjectStore().load(entry_id)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _assessment(url: str, profile: CrawlProfile) -> Assessment:
    try:
        return assess_url(url, crawl_profile=profile)
    except (UnsafeTargetError, CollectionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/assess")
def crawl_assess(
    url: str = Query(min_length=1, max_length=2048),
    crawl_profile: str = Query(default="quick", max_length=16),
    max_pages: int | None = Query(default=None),
    max_depth: int | None = Query(default=None),
) -> dict[str, object]:
    active = _profile(crawl_profile, max_pages, max_depth)
    return _assessment(url, active).model_dump(mode="json")


@router.get("/report", response_class=HTMLResponse)
def crawl_report(
    url: str = Query(min_length=1, max_length=2048),
    crawl_profile: str = Query(default="quick", max_length=16),
    max_pages: int | None = Query(default=None),
    max_depth: int | None = Query(default=None),
    profile: str | None = Query(default=None, max_length=24),
) -> str:
    active = _profile(crawl_profile, max_pages, max_depth)
    return render_report(_assessment(url, active), _report_profile(profile))


@router.get("/report.pdf")
def crawl_report_pdf(
    url: str = Query(min_length=1, max_length=2048),
    crawl_profile: str = Query(default="quick", max_length=16),
    max_pages: int | None = Query(default=None),
    max_depth: int | None = Query(default=None),
    profile: str | None = Query(default=None, max_length=24),
) -> Response:
    active = _profile(crawl_profile, max_pages, max_depth)
    assessment = _assessment(url, active)
    try:
        document = render_pdf(
            render_report(assessment, _report_profile(profile)),
            target=str(assessment.target),
        )
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


@router.get("/export")
def crawl_export(
    url: str = Query(min_length=1, max_length=2048),
    crawl_profile: str = Query(default="quick", max_length=16),
    max_pages: int | None = Query(default=None),
    max_depth: int | None = Query(default=None),
    profile: str | None = Query(default=None, max_length=24),
) -> Response:
    active = _profile(crawl_profile, max_pages, max_depth)
    package = build_evidence_package(
        _assessment(url, active),
        _report_profile(profile),
    )
    return Response(
        content=package.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/projects/{entry_id}/assess")
def project_crawl_assess(entry_id: str) -> dict[str, object]:
    project = _project(entry_id)
    return _assessment(
        project.target_url,
        project.resolved_crawl_profile(),
    ).model_dump(mode="json")


@router.get("/projects/{entry_id}/report", response_class=HTMLResponse)
def project_crawl_report(entry_id: str) -> str:
    project = _project(entry_id)
    assessment = _assessment(project.target_url, project.resolved_crawl_profile())
    return render_report(assessment, _report_profile(project.profile_id))


@router.get("/projects/{entry_id}/export")
def project_crawl_export(entry_id: str) -> Response:
    project = _project(entry_id)
    package = build_evidence_package(
        _assessment(project.target_url, project.resolved_crawl_profile()),
        _report_profile(project.profile_id),
    )
    return Response(
        content=package.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
