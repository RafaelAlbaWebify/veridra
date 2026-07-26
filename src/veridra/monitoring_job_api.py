from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .identity_tenancy import RequestIdentity, TenantCapability
from .monitoring_jobs import MonitoringJob, MonitoringJobError, SQLiteMonitoringJobStore
from .request_security import require_request_capability
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/api/tenant/monitoring-jobs", tags=["tenant-monitoring-jobs"])
MonitoringReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
MonitoringManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_monitoring)),
]


class MonitoringJobEnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: str = Field(min_length=24, max_length=24)
    run_window: str = Field(min_length=1, max_length=160)
    max_attempts: int = Field(default=3, ge=1, le=10)


class MonitoringJobResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    project_id: str
    run_window: str
    state: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    last_error: str | None
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


def _store(request: Request) -> SQLiteMonitoringJobStore:
    return SQLiteMonitoringJobStore(_root(request) / "monitoring-jobs.sqlite3")


def _response(job: MonitoringJob) -> MonitoringJobResponse:
    return MonitoringJobResponse(
        id=job.id,
        project_id=job.project_id,
        run_window=job.run_window,
        state=job.state.value,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        next_attempt_at=job.next_attempt_at,
        lease_expires_at=job.lease_expires_at,
        last_error=job.last_error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _require_project(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
) -> None:
    projects = TenantProjectStore(_root(request))
    try:
        projects.load(identity, projects.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from exc


@router.get("", response_model=list[MonitoringJobResponse])
def list_monitoring_jobs(
    request: Request,
    identity: MonitoringReader,
) -> list[MonitoringJobResponse]:
    return [_response(job) for job in _store(request).list_for_tenant(identity.tenant_id)]


@router.post("", response_model=MonitoringJobResponse, status_code=status.HTTP_201_CREATED)
def enqueue_monitoring_job(
    payload: MonitoringJobEnqueueRequest,
    request: Request,
    identity: MonitoringManager,
) -> MonitoringJobResponse:
    _require_project(request, identity, payload.project_id)
    try:
        job = _store(request).enqueue(
            tenant_id=identity.tenant_id,
            project_id=payload.project_id,
            run_window=payload.run_window,
            max_attempts=payload.max_attempts,
            now=datetime.now(UTC),
        )
    except MonitoringJobError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _response(job)


@router.delete("/{job_id}", response_model=MonitoringJobResponse)
def cancel_monitoring_job(
    job_id: str,
    request: Request,
    identity: MonitoringManager,
) -> MonitoringJobResponse:
    try:
        job = _store(request).cancel(
            tenant_id=identity.tenant_id,
            job_id=job_id,
            now=datetime.now(UTC),
        )
    except MonitoringJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitoring job not found.",
        ) from exc
    return _response(job)
