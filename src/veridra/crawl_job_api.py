from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .crawl_jobs import CrawlJob, CrawlJobError, SQLiteCrawlJobStore
from .identity_tenancy import RequestIdentity, TenantCapability
from .project_store import ClientProject
from .request_security import require_request_capability
from .tenant_entitlements import (
    release_tenant_usage_reservation,
    reserve_tenant_usage,
    tenant_workspace_active,
)
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .tenant_workspace_policy import TenantWorkspacePolicy
from .workspace_policy import PLAN_CATALOGUE, UsageKind, WorkspaceStatus

router = APIRouter(prefix="/api/tenant/crawl-jobs", tags=["tenant-crawl-jobs"])

CrawlJobReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
CrawlJobManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.run_assessments)),
]

_RESERVATION_LIFETIME = timedelta(hours=24)


class CrawlJobEnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: str = Field(min_length=24, max_length=24)
    request_key: str = Field(min_length=1, max_length=160)
    max_attempts: int = Field(default=3, ge=1, le=5)


class CrawlJobResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    project_id: str
    target_url: str
    crawl_profile: str
    page_budget: int
    pages_completed: int
    state: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    last_error: str | None
    assessment_id: str | None
    created_at: datetime
    updated_at: datetime


def _root(request: Request) -> Path:
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    if not isinstance(configured, Path):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant data storage is not configured.",
        )
    return configured


def _store(request: Request) -> SQLiteCrawlJobStore:
    return SQLiteCrawlJobStore(_root(request) / "crawl-jobs.sqlite3")


def _response(job: CrawlJob) -> CrawlJobResponse:
    return CrawlJobResponse(
        id=job.id,
        project_id=job.project_id,
        target_url=job.target_url,
        crawl_profile=job.crawl_profile,
        page_budget=job.page_budget,
        pages_completed=job.pages_completed,
        state=job.state.value,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        next_attempt_at=job.next_attempt_at,
        lease_expires_at=job.lease_expires_at,
        last_error=job.last_error,
        assessment_id=job.assessment_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _project(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
) -> ClientProject:
    projects = TenantProjectStore(_root(request))
    try:
        return projects.load(identity, projects.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from exc


def _max_active_jobs(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
) -> int:
    if not tenant_workspace_active(policy, identity):
        return 1
    workspace = policy.load(identity)
    if workspace.status is not WorkspaceStatus.active:
        raise HTTPException(status_code=403, detail="The workspace is suspended.")
    return PLAN_CATALOGUE[workspace.plan].max_concurrent_crawl_jobs


def _release(
    policy: TenantWorkspacePolicy,
    identity: RequestIdentity,
    *reservation_ids: str | None,
) -> None:
    for reservation_id in reservation_ids:
        if reservation_id:
            release_tenant_usage_reservation(policy, identity, reservation_id)


@router.get("", response_model=list[CrawlJobResponse])
def list_crawl_jobs(
    request: Request,
    identity: CrawlJobReader,
) -> list[CrawlJobResponse]:
    return [_response(job) for job in _store(request).list_for_tenant(identity.tenant_id)]


@router.post("", response_model=CrawlJobResponse, status_code=status.HTTP_201_CREATED)
def enqueue_crawl_job(
    payload: CrawlJobEnqueueRequest,
    request: Request,
    identity: CrawlJobManager,
) -> CrawlJobResponse:
    project = _project(request, identity, payload.project_id)
    profile = project.resolved_crawl_profile()
    page_budget = profile.limits.max_pages
    store = _store(request)

    existing = store.find_by_request(
        tenant_id=identity.tenant_id,
        project_id=payload.project_id,
        target_url=project.target_url,
        crawl_profile=profile.name.value,
        page_budget=page_budget,
        request_key=payload.request_key,
    )
    if existing is not None:
        return _response(existing)

    policy = TenantWorkspacePolicy(_root(request))
    max_active = _max_active_jobs(policy, identity)
    audit_reservation = ""
    page_reservation = ""
    try:
        audit_reservation = reserve_tenant_usage(
            policy,
            identity,
            UsageKind.audit,
            lifetime=_RESERVATION_LIFETIME,
        )
        page_reservation = reserve_tenant_usage(
            policy,
            identity,
            UsageKind.crawled_page,
            quantity=page_budget,
            lifetime=_RESERVATION_LIFETIME,
        )
    except HTTPException:
        existing = store.find_by_request(
            tenant_id=identity.tenant_id,
            project_id=payload.project_id,
            target_url=project.target_url,
            crawl_profile=profile.name.value,
            page_budget=page_budget,
            request_key=payload.request_key,
        )
        if existing is not None:
            _release(policy, identity, audit_reservation, page_reservation)
            return _response(existing)
        _release(policy, identity, audit_reservation, page_reservation)
        raise

    try:
        job, created = store.enqueue_with_status(
            tenant_id=identity.tenant_id,
            project_id=payload.project_id,
            target_url=project.target_url,
            crawl_profile=profile.name.value,
            page_budget=page_budget,
            request_key=payload.request_key,
            now=datetime.now(UTC),
            max_attempts=payload.max_attempts,
            max_active_for_tenant=max_active,
            audit_reservation_id=audit_reservation or None,
            page_reservation_id=page_reservation or None,
        )
    except CrawlJobError as exc:
        _release(policy, identity, audit_reservation, page_reservation)
        if "concurrency allowance" in str(exc):
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not created:
        _release(policy, identity, audit_reservation, page_reservation)
    return _response(job)


@router.delete("/{job_id}", response_model=CrawlJobResponse)
def cancel_crawl_job(
    job_id: str,
    request: Request,
    identity: CrawlJobManager,
) -> CrawlJobResponse:
    store = _store(request)
    try:
        job = store.cancel(
            tenant_id=identity.tenant_id,
            job_id=job_id,
            now=datetime.now(UTC),
        )
    except CrawlJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crawl job not found.",
        ) from exc
    policy = TenantWorkspacePolicy(_root(request))
    _release(
        policy,
        identity,
        job.audit_reservation_id,
        job.page_reservation_id,
    )
    return _response(job)
