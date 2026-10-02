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
from .runtime_config import RuntimeConfig, RuntimeEnvironment
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_monitoring_execution import execute_monitoring_for_identity
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .workspace_policy import WorkspacePolicyError

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
    config = getattr(request.app.state, "veridra_runtime_config", None)
    enforce_entitlements = (
        isinstance(config, RuntimeConfig)
        and config.environment is RuntimeEnvironment.production
    )
    try:
        result = execute_monitoring_for_identity(
            root=_root(request) or TenantProjectStore().root,
            identity=identity,
            project_id=project_id,
            enforce_entitlements=enforce_entitlements,
        )
    except WorkspacePolicyError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (UnsafeTargetError, CollectionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TenantProjectStoreError, TenantHistoryStoreError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from exc
    return MonitoringRunResult(
        project_id=project_id,
        assessment_id=result.assessment_id,
        email_status=result.email_status,
        email_error=result.email_error,
    )
