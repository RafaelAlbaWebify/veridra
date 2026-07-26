from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from .core import Assessment
from .exports import build_evidence_package
from .identity_tenancy import RequestIdentity, TenantCapability
from .pdf_reports import PdfRenderError, render_pdf
from .report_profiles import DEFAULT_REPORT_PROFILE, ReportProfile
from .reports import render_report
from .request_security import require_request_capability
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_profile_store import TenantProfileStore, TenantProfileStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

ReportManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_reports)),
]

router = APIRouter(
    prefix="/api/tenant/projects/{project_id}/assessments/{assessment_id}",
    tags=["tenant-reports"],
)


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _context(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
    assessment_id: str,
) -> tuple[Assessment, ReportProfile]:
    root = _root(request)
    projects = TenantProjectStore(root)
    history = TenantHistoryStore(root)
    profiles = TenantProfileStore(root)
    try:
        project = projects.load(identity, projects.ref(identity, project_id))
        assessment = history.load(
            identity,
            history.ref(identity, project_id, assessment_id),
        )
        profile = (
            DEFAULT_REPORT_PROFILE
            if project.profile_id is None
            else profiles.load(identity, profiles.ref(identity, project.profile_id))
        )
    except (
        TenantProjectStoreError,
        TenantHistoryStoreError,
        TenantProfileStoreError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report source not found.",
        ) from exc
    return assessment, profile


@router.get("/report", response_class=HTMLResponse)
def render_tenant_report(
    project_id: str,
    assessment_id: str,
    request: Request,
    identity: ReportManager,
) -> str:
    assessment, profile = _context(
        request,
        identity,
        project_id,
        assessment_id,
    )
    return render_report(assessment, profile)


@router.get("/report.pdf")
def render_tenant_report_pdf(
    project_id: str,
    assessment_id: str,
    request: Request,
    identity: ReportManager,
) -> Response:
    assessment, profile = _context(
        request,
        identity,
        project_id,
        assessment_id,
    )
    try:
        document = render_pdf(
            render_report(assessment, profile),
            target=str(assessment.target),
        )
    except PdfRenderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
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
def export_tenant_report_evidence(
    project_id: str,
    assessment_id: str,
    request: Request,
    identity: ReportManager,
) -> Response:
    assessment, profile = _context(
        request,
        identity,
        project_id,
        assessment_id,
    )
    package = build_evidence_package(assessment, profile)
    return Response(
        content=package.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
