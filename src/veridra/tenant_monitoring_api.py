from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr

from .collector import CollectionError
from .core import UnsafeTargetError
from .email_delivery import (
    EmailAttemptStore,
    EmailDeliveryError,
    EmailStatus,
    send_monitoring_summary,
)
from .identity_tenancy import RequestIdentity, TenantCapability
from .monitoring_schedule import MonitoringSchedule
from .project_store import ClientProject
from .request_security import require_request_capability
from .service import assess_url
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError

router = APIRouter(prefix="/api/tenant/monitoring", tags=["tenant-monitoring"])
MonitoringReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
MonitoringManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_monitoring)),
]


class MonitoringConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    schedule: MonitoringSchedule
    recipient: EmailStr | None = None


class MonitoringConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: MonitoringSchedule
    recipient: EmailStr | None = None


class MonitoringRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    assessment_id: str
    email_status: EmailStatus | None = None
    email_error: str | None = None


def _root(request: Request) -> Path | None:
    configured = getattr(request.app.state, "veridra_tenant_data_root", None)
    return configured if isinstance(configured, Path) else None


def _store(request: Request) -> TenantProjectStore:
    return TenantProjectStore(_root(request))


def _load(
    request: Request,
    identity: RequestIdentity,
    project_id: str,
) -> ClientProject:
    store = _store(request)
    try:
        return store.load(identity, store.ref(identity, project_id))
    except TenantProjectStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from exc


@router.get("/{project_id}", response_model=MonitoringConfiguration)
def get_monitoring_configuration(
    project_id: str,
    request: Request,
    identity: MonitoringReader,
) -> MonitoringConfiguration:
    project = _load(request, identity, project_id)
    return MonitoringConfiguration(
        project_id=project_id,
        schedule=project.monitoring_schedule,
        recipient=project.monitoring_email,
    )


@router.put("/{project_id}", response_model=MonitoringConfiguration)
def replace_monitoring_configuration(
    project_id: str,
    payload: MonitoringConfigurationUpdate,
    request: Request,
    identity: MonitoringManager,
) -> MonitoringConfiguration:
    project = _load(request, identity, project_id)
    replacement = ClientProject.model_validate(
        project.model_copy(
            update={
                "monitoring_schedule": payload.schedule,
                "monitoring_email": payload.recipient,
            }
        )
    )
    store = _store(request)
    try:
        replacement_id = store.replace(
            identity,
            store.ref(identity, project_id),
            replacement,
        )
    except TenantProjectStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from exc
    return MonitoringConfiguration(
        project_id=replacement_id,
        schedule=replacement.monitoring_schedule,
        recipient=replacement.monitoring_email,
    )


@router.post("/{project_id}/run", response_model=MonitoringRunResult)
def run_monitoring_assessment(
    project_id: str,
    request: Request,
    identity: MonitoringManager,
) -> MonitoringRunResult:
    project = _load(request, identity, project_id)
    try:
        assessment = assess_url(
            project.target_url,
            crawl_profile=project.resolved_crawl_profile(),
        )
    except (UnsafeTargetError, CollectionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    root = _root(request)
    history = TenantHistoryStore(root)
    try:
        assessment_id = history.save(identity, project_id, assessment)
    except TenantHistoryStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from exc

    email_status: EmailStatus | None = None
    email_error: str | None = None
    tenant_root = history.root / identity.tenant_id
    try:
        attempt = send_monitoring_summary(
            project_id=project_id,
            project_name=project.name,
            target_url=project.target_url,
            assessment_id=assessment_id,
            assessment=assessment,
            recipient=(
                str(project.monitoring_email)
                if project.monitoring_email is not None
                else None
            ),
            store=EmailAttemptStore(tenant_root / "email-deliveries"),
        )
        if attempt is not None:
            email_status = attempt.status
            email_error = attempt.error or None
    except EmailDeliveryError as exc:
        email_status = EmailStatus.failed
        email_error = str(exc)

    return MonitoringRunResult(
        project_id=project_id,
        assessment_id=assessment_id,
        email_status=email_status,
        email_error=email_error,
    )
