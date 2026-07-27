from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .core import Assessment
from .identity_tenancy import RequestIdentity, TenantCapability
from .project_store import ClientProject
from .request_security import require_request_capability
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_project_store import TenantProjectStore, TenantProjectStoreError
from .workspace_web import require_project_capacity

ProjectManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_projects)),
]


class AssessmentProjectConversion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    assessment: Assessment
    project_name: str = Field(min_length=1, max_length=120)
    client_label: str | None = Field(default=None, max_length=120)
    profile_id: str | None = Field(default=None, min_length=24, max_length=24)


class AssessmentProjectCreated(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    assessment_id: str


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


router = APIRouter(tags=["assessment-project-conversion"])


@router.post(
    "/api/tenant/projects/from-assessment",
    response_model=AssessmentProjectCreated,
    status_code=status.HTTP_201_CREATED,
)
def convert_assessment_to_project(
    payload: AssessmentProjectConversion,
    request: Request,
    identity: ProjectManager,
) -> AssessmentProjectCreated:
    root = _root(request)
    projects = TenantProjectStore(root)
    history = TenantHistoryStore(root)
    require_project_capacity(len(projects.list(identity)))
    project = ClientProject.build(
        name=payload.project_name,
        target_url=str(payload.assessment.target),
        client_label=payload.client_label,
        profile_id=payload.profile_id,
    )
    try:
        project_id = projects.save(identity, project)
    except TenantProjectStoreError as exc:
        raise HTTPException(status_code=404, detail="Report profile not found.") from exc
    try:
        assessment_id = history.save(identity, project_id, payload.assessment)
    except TenantHistoryStoreError as exc:
        projects.delete(identity, projects.ref(identity, project_id))
        raise HTTPException(
            status_code=500,
            detail="Project conversion could not be completed.",
        ) from exc
    return AssessmentProjectCreated(
        project_id=project_id,
        assessment_id=assessment_id,
    )
