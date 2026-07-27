from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from .app import dashboard
from .collector import CollectionError
from .core import Assessment, UnsafeTargetError, demo_assessment
from .exports import build_evidence_package
from .profile_store import ProfileStore
from .report_profiles import ReportProfile
from .reports import render_report
from .tenant_assessment_usage import assess_for_request

router = APIRouter(tags=["tenant-assessments"])


def _profile(profile: str | None) -> ReportProfile:
    from .app import _resolve_profile

    return _resolve_profile(profile)


def _assessment(
    request: Request,
    url: str | None,
    demo: bool,
) -> Assessment:
    if demo:
        return demo_assessment()
    if url is None:
        raise HTTPException(status_code=400, detail="A target URL is required.")
    try:
        return assess_for_request(request, url)
    except (UnsafeTargetError, CollectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/assess")
def assess(
    request: Request,
    url: str = Query(min_length=1, max_length=2048),
) -> dict[str, object]:
    return _assessment(request, url, False).model_dump(mode="json")


@router.get("/report", response_class=HTMLResponse)
def report(
    request: Request,
    url: str | None = Query(default=None, min_length=1, max_length=2048),
    demo: bool = False,
    profile: str | None = Query(default=None, max_length=24),
) -> str:
    return render_report(_assessment(request, url, demo), _profile(profile))


@router.get("/export")
def export(
    request: Request,
    url: str | None = Query(default=None, min_length=1, max_length=2048),
    demo: bool = False,
    profile: str | None = Query(default=None, max_length=24),
) -> Response:
    package = build_evidence_package(
        _assessment(request, url, demo),
        _profile(profile),
    )
    return Response(
        content=package.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    url: str | None = Query(default=None, min_length=1, max_length=2048),
    demo: bool = False,
    area: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    profile: str | None = Query(default=None, max_length=24),
) -> str:
    selected_profile = _profile(profile)
    entries = ProfileStore().list()
    if demo or url is None:
        return dashboard(
            demo_assessment(),
            demo_mode=True,
            area=area,
            status=status,
            selected_profile=profile,
            profile_entries=entries,
        )
    try:
        return dashboard(
            assess_for_request(request, url),
            submitted_url=url,
            area=area,
            status=status,
            selected_profile=profile,
            profile_entries=entries,
        )
    except (UnsafeTargetError, CollectionError) as exc:
        return dashboard(
            demo_assessment(),
            submitted_url=url,
            error=str(exc),
            demo_mode=True,
            area=area,
            status=status,
            selected_profile=profile,
            profile_entries=entries,
        )
    finally:
        del selected_profile
