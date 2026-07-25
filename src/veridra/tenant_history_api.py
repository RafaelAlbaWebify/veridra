from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from .core import Assessment
from .history import Comparison, HistoryEntry
from .identity_tenancy import RequestIdentity, TenantCapability
from .request_security import require_request_capability
from .tenant_history_store import TenantHistoryStore, TenantHistoryStoreError

HistoryReader = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.view_data)),
]
HistoryWriter = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.run_assessments)),
]
HistoryManager = Annotated[
    RequestIdentity,
    Depends(require_request_capability(TenantCapability.manage_reports)),
]


class AssessmentCreated(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str


class AssessmentSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    target: str
    generated_at: str
    mode: str
    total_findings: int

    @classmethod
    def from_entry(cls, entry: HistoryEntry) -> AssessmentSummary:
        return cls(
            id=entry.id,
            target=entry.target,
            generated_at=entry.generated_at,
            mode=entry.mode,
            total_findings=entry.total_findings,
        )


class AssessmentComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    before_id: str
    after_id: str
    added: tuple[str, ...]
    resolved: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]

    @classmethod
    def from_comparison(cls, comparison: Comparison) -> AssessmentComparison:
        return cls(**comparison.__dict__)


def _root(request: Request) -> Path | None:
    value = getattr(request.app.state, "veridra_tenant_data_root", None)
    return value if isinstance(value, Path) else None


def _store(request: Request) -> TenantHistoryStore:
    return TenantHistoryStore(_root(request))


def _not_found(exc: TenantHistoryStoreError) -> HTTPException:
    return HTTPException(status_code=404, detail="Assessment history not found.")


router = APIRouter(
    prefix="/api/tenant/projects/{project_id}/assessments",
    tags=["tenant-assessments"],
)


@router.get("", response_model=list[AssessmentSummary])
def list_assessments(
    project_id: str,
    request: Request,
    identity: HistoryReader,
) -> list[AssessmentSummary]:
    try:
        entries = _store(request).list(identity, project_id)
    except TenantHistoryStoreError as exc:
        raise _not_found(exc) from exc
    return [AssessmentSummary.from_entry(entry) for entry in entries]


@router.post("", response_model=AssessmentCreated, status_code=status.HTTP_201_CREATED)
def save_assessment(
    project_id: str,
    assessment: Assessment,
    request: Request,
    identity: HistoryWriter,
) -> AssessmentCreated:
    try:
        identifier = _store(request).save(identity, project_id, assessment)
    except TenantHistoryStoreError as exc:
        raise _not_found(exc) from exc
    return AssessmentCreated(id=identifier)


@router.get("/compare", response_model=AssessmentComparison)
def compare_assessments(
    project_id: str,
    request: Request,
    identity: HistoryReader,
    before: str = Query(min_length=24, max_length=24),
    after: str = Query(min_length=24, max_length=24),
) -> AssessmentComparison:
    try:
        comparison = _store(request).compare(identity, project_id, before, after)
    except TenantHistoryStoreError as exc:
        raise _not_found(exc) from exc
    return AssessmentComparison.from_comparison(comparison)


@router.get("/{assessment_id}", response_model=Assessment)
def load_assessment(
    project_id: str,
    assessment_id: str,
    request: Request,
    identity: HistoryReader,
) -> Assessment:
    store = _store(request)
    try:
        return store.load(
            identity,
            store.ref(identity, project_id, assessment_id),
        )
    except TenantHistoryStoreError as exc:
        raise _not_found(exc) from exc


@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(
    project_id: str,
    assessment_id: str,
    request: Request,
    identity: HistoryManager,
) -> None:
    store = _store(request)
    try:
        store.delete(
            identity,
            store.ref(identity, project_id, assessment_id),
        )
    except TenantHistoryStoreError as exc:
        raise _not_found(exc) from exc
