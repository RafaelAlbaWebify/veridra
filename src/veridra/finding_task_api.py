from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .core import Finding
from .identity_tenancy import RequestIdentity, TenantCapability
from .request_security import require_request_capability
from .task_store import RemediationTask
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError
from .tenant_task_store import TenantTaskStore

TaskManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_tasks)),
]


class FindingTaskConversion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    assessment_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    finding_id: str = Field(min_length=1, max_length=160)


class FindingTaskCreated(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _finding_notes(finding: Finding) -> str:
    evidence = json.dumps(
        finding.evidence,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(evidence) > 1800:
        evidence = f"{evidence[:1797]}..."
    recommendation = finding.recommendation or "Review the supporting evidence."
    notes = (
        f"Area: {finding.area}\n"
        f"Severity: {finding.severity}\n"
        f"Observation: {finding.summary}\n"
        f"Recommended fix: {recommendation}\n"
        f"Evidence: {evidence}"
    )
    return notes[:5000]


def create_task_from_finding(
    payload: FindingTaskConversion,
    request: Request,
    identity: RequestIdentity,
) -> FindingTaskCreated:
    history = TenantHistoryStore(_root(request))
    try:
        assessment = history.load(
            identity,
            history.ref(identity, payload.project_id, payload.assessment_id),
        )
    except TenantHistoryStoreError as exc:
        raise HTTPException(status_code=404, detail="Finding source not found.") from exc
    finding = next(
        (item for item in assessment.findings if item.id == payload.finding_id),
        None,
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding source not found.")
    task = RemediationTask(
        project_id=payload.project_id,
        finding_id=finding.id,
        title=finding.title,
        notes=_finding_notes(finding),
        source_assessment_id=payload.assessment_id,
    )
    task_id = TenantTaskStore(_root(request)).save(identity, task)
    return FindingTaskCreated(task_id=task_id)


router = APIRouter(tags=["finding-remediation-tasks"])


@router.post(
    "/api/tenant/tasks/from-finding",
    response_model=FindingTaskCreated,
    status_code=status.HTTP_201_CREATED,
)
def convert_finding_to_task(
    payload: FindingTaskConversion,
    request: Request,
    identity: TaskManager,
) -> FindingTaskCreated:
    return create_task_from_finding(payload, request, identity)
