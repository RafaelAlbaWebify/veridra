from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from .collector import CollectionError
from .core import Assessment, UnsafeTargetError
from .crawl_profiles import CrawlProfile, resolve_crawl_profile
from .exports import build_evidence_package
from .identity_tenancy import RequestIdentity
from .pdf_reports import PdfRenderError, render_pdf
from .profile_store import ProfileStore, ProfileStoreError
from .project_store import ClientProject, ProjectStore, ProjectStoreError
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile
from .reports import render_report
from .service import assess_url
from .tenant_assessment_usage import crawled_page_count
from .tenant_entitlements import (
    record_tenant_usage,
    reserve_tenant_usage,
    tenant_workspace_active,
)
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import UsageKind

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


def _tenant_context(
    request: Request,
) -> tuple[TenantWorkspacePolicy, RequestIdentity] | None:
    identity = getattr(request.state, "veridra_verified_identity", None)
    if not isinstance(identity, RequestIdentity):
        return None
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    root = configured if isinstance(configured, Path) else None
    policy = TenantWorkspacePolicy(root)
    if not tenant_workspace_active(policy, identity):
        return None
    return policy, identity


def _reserve(request: Request, kind: UsageKind, *, quantity: int = 1) -> None:
    context = _tenant_context(request)
    if context is not None:
        reserve_tenant_usage(context[0], context[1], kind, quantity=quantity)


def _record(
    request: Request,
    kind: UsageKind,
    *,
    quantity: int = 1,
    related_id: str = "",
    note: str = "",
) -> None:
    context = _tenant_context(request)
    if context is not None:
        record_tenant_usage(
            context[0],
            context[1],
            kind,
            quantity=quantity,
            related_id=related_id,
            note=note,
        )


def _assessment(url: str, profile: CrawlProfile, request: Request) -> Assessment:
    _reserve(request, UsageKind.audit)
    _reserve(request, UsageKind.crawled_page, quantity=profile.limits.max_pages)
    try:
        assessment = assess_url(url, crawl_profile=profile)
    except (UnsafeTargetError, CollectionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    correlation = str(assessment.target)
    _record(request, UsageKind.audit, related_id=correlation, note=profile.name.value)
    _record(
        request,
        UsageKind.crawled_page,
        quantity=crawled_page_count(assessment),
        related_id=correlation,
        note=f"Successful {profile.name.value} crawl pages",
    )
    return assessment


@router.get("/assess")
def crawl_assess(
    request: Request,
    url: str = Query(min_length=1, max_length=2048),
    crawl_profile: str = Query(default="quick", max_length=16),
    max_pages: int | None = Query(default=None),
    max_depth: int | None = Query(default=None),
) -> dict[str, object]:
    active = _profile(crawl_profile, max_pages, max_depth)
    return _assessment(url, active, request).model_dump(mode="json")


@router.get("/report", response_class=HTMLResponse)
def crawl_report(
    request: Request,
    url: str = Query(min_length=1, max_length=2048),
    crawl_profile: str = Query(default="quick", max_length=16),
    max_pages: int | None = Query(default=None),
    max_depth: int | None = Query(default=None),
    profile: str | None = Query(default=None, max_length=24),
) -> str:
    active = _profile(crawl_profile, max_pages, max_depth)
    return render_report(_assessment(url, active, request), _report_profile(profile))


@router.get("/report.pdf")
def crawl_report_pdf(
    request: Request,
    url: str = Query(min_length=1, max_length=2048),
    crawl_profile: str = Query(default="quick", max_length=16),
    max_pages: int | None = Query(default=None),
    max_depth: int | None = Query(default=None),
    profile: str | None = Query(default=None, max_length=24),
) -> Response:
    _reserve(request, UsageKind.pdf)
    active = _profile(crawl_profile, max_pages, max_depth)
    assessment = _assessment(url, active, request)
    try:
        document = render_pdf(
            render_report(assessment, _report_profile(profile)),
            target=str(assessment.target),
        )
    except PdfRenderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _record(request, UsageKind.pdf, related_id=str(assessment.target))
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
    request: Request,
    url: str = Query(min_length=1, max_length=2048),
    crawl_profile: str = Query(default="quick", max_length=16),
    max_pages: int | None = Query(default=None),
    max_depth: int | None = Query(default=None),
    profile: str | None = Query(default=None, max_length=24),
) -> Response:
    _reserve(request, UsageKind.export)
    active = _profile(crawl_profile, max_pages, max_depth)
    assessment = _assessment(url, active, request)
    package = build_evidence_package(assessment, _report_profile(profile))
    _record(request, UsageKind.export, related_id=str(assessment.target))
    return Response(
        content=package.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/projects/{entry_id}/assess")
def project_crawl_assess(entry_id: str, request: Request) -> dict[str, object]:
    project = _project(entry_id)
    return _assessment(
        project.target_url,
        project.resolved_crawl_profile(),
        request,
    ).model_dump(mode="json")


@router.get("/projects/{entry_id}/report", response_class=HTMLResponse)
def project_crawl_report(entry_id: str, request: Request) -> str:
    project = _project(entry_id)
    assessment = _assessment(
        project.target_url,
        project.resolved_crawl_profile(),
        request,
    )
    return render_report(assessment, _report_profile(project.profile_id))


@router.get("/projects/{entry_id}/export")
def project_crawl_export(entry_id: str, request: Request) -> Response:
    _reserve(request, UsageKind.export)
    project = _project(entry_id)
    assessment = _assessment(
        project.target_url,
        project.resolved_crawl_profile(),
        request,
    )
    package = build_evidence_package(assessment, _report_profile(project.profile_id))
    _record(request, UsageKind.export, related_id=str(assessment.target))
    return Response(
        content=package.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
